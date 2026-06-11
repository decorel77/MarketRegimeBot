import contextlib
import io
import json
import unittest
from unittest import mock

from tools import regime_autocycle
from utils import guardrails


class StartupGuardrailTests(unittest.TestCase):
    def test_guardrail_passes_when_broker_packages_not_importable(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            guardrails.run_all_checks()

    def test_guardrail_fails_when_broker_package_is_importable(self):
        def fake_find_spec(name: str):
            return object() if name == "ib_insync" else None

        with mock.patch("importlib.util.find_spec", side_effect=fake_find_spec):
            with self.assertRaises(guardrails.GuardrailViolation) as ctx:
                guardrails.run_all_checks()

        self.assertIn("ib_insync", str(ctx.exception))

    def test_autocycle_calls_guardrail_before_cycle(self):
        output = io.StringIO()
        with mock.patch("tools.regime_autocycle.run_all_checks") as run_checks:
            with mock.patch(
                "tools.regime_autocycle.run_regime_cycle",
                return_value={
                    "status": "SAFE_DRY_RUN_REGIME",
                    "dry_run": True,
                    "regime": "UNKNOWN",
                    "confidence": 0,
                },
            ) as run_cycle:
                with contextlib.redirect_stdout(output):
                    exit_code = regime_autocycle.main(["--once"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")
        run_checks.assert_called_once_with()
        run_cycle.assert_called_once_with(write_snapshot=True)

    def test_autocycle_stops_before_cycle_when_guardrail_fails(self):
        with mock.patch(
            "tools.regime_autocycle.run_all_checks",
            side_effect=guardrails.GuardrailViolation("ib_insync"),
        ) as run_checks:
            with mock.patch("tools.regime_autocycle.run_regime_cycle") as run_cycle:
                with self.assertRaises(guardrails.GuardrailViolation):
                    regime_autocycle.main(["--once"])

        run_checks.assert_called_once_with()
        run_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
