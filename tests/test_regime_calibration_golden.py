"""Golden test for the HWL-005 calibration-config extraction.

Proves the extraction of ``regime_model_v2``'s calibration constants into
``core/regime_calibration.py`` is **byte-identical** — classification, confidence,
risk level, reason strings, composite score, and the factor functions all
reproduce the golden snapshot captured from the pre-refactor code
(``tests/fixtures/regime_v2_calibration_golden.json``).

A diff here means classification behaviour changed — it must NOT be silenced by
regenerating the fixture; investigate first (a regime mis-emit silently hard-stops
the live bot).

Broker-free and hermetic: imports only ``regime_model_v2`` (no snapshot write, no
pandas, no ``discover``). Run focused:
    python -S -m unittest tests.test_regime_calibration_golden
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core import regime_calibration as cal  # noqa: E402
from core import regime_model_v2 as m  # noqa: E402

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "regime_v2_calibration_golden.json"

# The full set of constants the extraction moved.
_CONSTANT_NAMES = (
    "SHORT_WINDOW", "DRAWDOWN_NORMALISE", "MA_GAP_NORMALISE",
    "WEIGHT_TREND", "WEIGHT_MA_GAP", "WEIGHT_MOMENTUM",
    "VOL_HIGH_THRESHOLD", "VOL_ELEVATED_THRESHOLD", "DRAWDOWN_SEVERE_THRESHOLD",
    "COMPOSITE_BULL_THRESHOLD", "COMPOSITE_BEAR_THRESHOLD", "BEAR_DRAWDOWN_QUALIFIER",
)


class GoldenSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))

    def test_model_version_matches(self) -> None:
        self.assertEqual(m.MODEL_VERSION, self.golden["model_version"])

    def test_classification_cases_byte_identical(self) -> None:
        for case in self.golden["cases"]:
            with self.subTest(inputs=case["in"]):
                inp = m.RegimeInputV2(*case["in"])
                result = m.classify_regime_v2(inp)
                self.assertEqual(result.market_regime, case["regime"])
                self.assertEqual(result.confidence, case["confidence"])
                self.assertEqual(result.risk_level, case["risk"])
                self.assertEqual(list(result.reason), case["reason"])
                self.assertEqual(m.composite_score(inp), case["composite"])

    def test_factor_functions_byte_identical(self) -> None:
        for fset in self.golden["factors"]:
            closes = fset["closes"]
            with self.subTest(closes=closes):
                self.assertEqual(m._drawdown_score(closes), fset["drawdown"])
                self.assertEqual(m._ma_gap_score(closes), fset["ma_gap"])
                self.assertEqual(m._momentum_score(closes), fset["momentum"])


class CalibrationReexportTest(unittest.TestCase):
    def test_model_reexports_calibration_identically(self) -> None:
        for name in _CONSTANT_NAMES:
            with self.subTest(constant=name):
                self.assertIs(getattr(m, name), getattr(cal, name),
                              f"{name} re-export drifted from regime_calibration")

    def test_no_literal_redefinition_left_in_model(self) -> None:
        # The model module must NOT redefine the calibration literals (they now
        # live only in regime_calibration). Guards against a silent fork.
        src = (REPO / "core" / "regime_model_v2.py").read_text(encoding="utf-8")
        for name in _CONSTANT_NAMES:
            self.assertNotIn(f"\n{name} = ", src,
                             f"{name} is redefined in regime_model_v2.py — should import only")


if __name__ == "__main__":
    unittest.main()
