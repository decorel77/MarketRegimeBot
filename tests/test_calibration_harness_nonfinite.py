"""REGIME-CAL-001: non-finite fail-closed tests for the calibration harness.

Separate stdlib ``unittest`` module (no pytest / conftest / tools imports) so it
runs under ``python -S -m unittest`` without the broker-free env needing pytest.

Scope: ``History.from_rows`` only, with injected in-memory rows. No CSV/JSON file
load, no download, no ``run_regime_cycle``, no export write -- purely the row
normalizer's fail-closed behavior on non-finite prices.
"""

from __future__ import annotations

import math
import unittest

from research import calibration_harness as ch


def _rows(n: int) -> list[dict[str, str]]:
    """Minimal valid synthetic rows (strictly increasing ISO dates, positive prices)."""
    out: list[dict[str, str]] = []
    for d in range(n):
        out.append(
            {
                "date": f"2026-01-{d + 1:02d}",
                "spy_close": f"{100.0 + d:.4f}",
                "qqq_close": f"{300.0 + d:.4f}",
                "vix_close": "18.0",
            }
        )
    return out


class CalibrationFromRowsNonFiniteTests(unittest.TestCase):
    def test_valid_rows_still_build(self) -> None:
        history = ch.History.from_rows(_rows(ch.MIN_BARS))
        self.assertEqual(len(history.spy_close), ch.MIN_BARS)
        self.assertTrue(all(math.isfinite(v) for v in history.spy_close))

    def test_non_finite_cell_fails_closed_in_full_history(self) -> None:
        for bad in (float("inf"), float("-inf"), float("nan")):
            for column in ("spy_close", "qqq_close", "vix_close"):
                with self.subTest(bad=bad, column=column):
                    rows = _rows(ch.MIN_BARS)
                    rows[3][column] = bad  # inject a non-finite float cell
                    with self.assertRaises(ch.CalibrationDataError):
                        ch.History.from_rows(rows)

    def test_non_finite_string_cell_fails_closed(self) -> None:
        # float("inf")/"nan"/"Infinity" parse successfully -- must still be rejected.
        for bad in ("inf", "-inf", "Infinity", "nan", "NaN"):
            with self.subTest(bad=bad):
                rows = _rows(ch.MIN_BARS)
                rows[5]["spy_close"] = bad
                with self.assertRaises(ch.CalibrationDataError):
                    ch.History.from_rows(rows)

    def test_non_finite_reason_not_masked_by_short_history(self) -> None:
        # Even below MIN_BARS, a non-finite cell must raise the non-finite reason
        # (the length gate no longer masks it).
        rows = _rows(3)
        rows[1]["spy_close"] = float("inf")
        with self.assertRaises(ch.CalibrationDataError) as ctx:
            ch.History.from_rows(rows)
        self.assertIn("non-finite", str(ctx.exception))

    def test_non_numeric_cell_still_fails_closed(self) -> None:
        rows = _rows(ch.MIN_BARS)
        rows[2]["spy_close"] = "not-a-price"
        with self.assertRaises(ch.CalibrationDataError):
            ch.History.from_rows(rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
