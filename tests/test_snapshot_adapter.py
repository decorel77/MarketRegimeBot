"""Tests for core/snapshot_adapter.py — Phase 3 snapshot input loading."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput
from core.snapshot_adapter import (
    _safe_load_json,
    _trend_from_allocation,
    _volatility_from_options,
    load_regime_input_from_snapshots,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _minimal_allocation(novabot_pct: float = 90.0) -> dict:
    return {
        "recommendation": {
            "recommended_allocation": {
                "NovaBotV2": novabot_pct,
                "NovaBotV2Options": 100.0 - novabot_pct,
                "NovaCryptoBot": 0.0,
                "CashReserve": 0.0,
            }
        }
    }


def _minimal_options(warnings: int = 1, chains: int = 8) -> dict:
    return {
        "health_metrics": {
            "warnings_count": warnings,
            "chains_loaded": chains,
            "signals_created": 1,
            "paper_decisions": 1,
        }
    }


# ---------------------------------------------------------------------------
# _safe_load_json
# ---------------------------------------------------------------------------

class SafeLoadJsonTests(unittest.TestCase):
    def test_returns_none_for_missing_file(self):
        self.assertIsNone(_safe_load_json(Path("/nonexistent/path/file.json")))

    def test_returns_none_for_corrupt_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("{not valid json")
            tmp = Path(f.name)
        try:
            self.assertIsNone(_safe_load_json(tmp))
        finally:
            tmp.unlink(missing_ok=True)

    def test_returns_none_for_json_array(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("[1, 2, 3]")
            tmp = Path(f.name)
        try:
            self.assertIsNone(_safe_load_json(tmp))
        finally:
            tmp.unlink(missing_ok=True)

    def test_returns_dict_for_valid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write('{"key": "value"}')
            tmp = Path(f.name)
        try:
            result = _safe_load_json(tmp)
            self.assertEqual(result, {"key": "value"})
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# _trend_from_allocation
# ---------------------------------------------------------------------------

class TrendExtractionTests(unittest.TestCase):
    def test_full_novabot_allocation_is_positive(self):
        score = _trend_from_allocation(_minimal_allocation(100.0))
        self.assertEqual(score, 1.0)

    def test_zero_novabot_allocation_is_negative(self):
        score = _trend_from_allocation(_minimal_allocation(0.0))
        self.assertEqual(score, -1.0)

    def test_fifty_percent_allocation_is_zero(self):
        score = _trend_from_allocation(_minimal_allocation(50.0))
        self.assertAlmostEqual(score, 0.0, places=2)

    def test_ninety_percent_allocation_is_bullish(self):
        score = _trend_from_allocation(_minimal_allocation(90.0))
        self.assertGreater(score, 0.5)

    def test_missing_recommendation_returns_none(self):
        self.assertIsNone(_trend_from_allocation({}))

    def test_trend_clamped_to_one(self):
        score = _trend_from_allocation(_minimal_allocation(100.0))
        self.assertLessEqual(score, 1.0)
        self.assertGreaterEqual(score, -1.0)

    def test_nan_allocation_fails_closed(self):
        # NaN/+-inf would otherwise survive the min/max clamp as a spurious
        # strong directional trend (NaN -> 1.0). Must fall back to None.
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=bad):
                self.assertIsNone(_trend_from_allocation(_minimal_allocation(bad)))

    def test_bool_allocation_fails_closed(self):
        self.assertIsNone(_trend_from_allocation(_minimal_allocation(True)))

    def test_string_allocation_returns_none(self):
        data = {"recommendation": {"recommended_allocation": {"NovaBotV2": "ninety"}}}
        self.assertIsNone(_trend_from_allocation(data))

    def test_non_mapping_allocation_returns_none(self):
        data = {"recommendation": {"recommended_allocation": ["NovaBotV2", 90]}}
        self.assertIsNone(_trend_from_allocation(data))


# ---------------------------------------------------------------------------
# _volatility_from_options
# ---------------------------------------------------------------------------

class VolatilityExtractionTests(unittest.TestCase):
    def test_no_warnings_is_zero(self):
        vol = _volatility_from_options(_minimal_options(warnings=0, chains=8))
        self.assertEqual(vol, 0.0)

    def test_one_warning_eight_chains_is_low(self):
        vol = _volatility_from_options(_minimal_options(warnings=1, chains=8))
        self.assertAlmostEqual(vol, 0.125, places=3)

    def test_many_warnings_capped_at_one(self):
        vol = _volatility_from_options(_minimal_options(warnings=100, chains=8))
        self.assertEqual(vol, 1.0)

    def test_missing_health_metrics_returns_none(self):
        self.assertIsNone(_volatility_from_options({}))

    def test_volatility_never_negative(self):
        vol = _volatility_from_options(_minimal_options(warnings=0, chains=100))
        self.assertGreaterEqual(vol, 0.0)

    def test_nan_inf_warnings_fail_closed(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=bad):
                self.assertIsNone(_volatility_from_options(_minimal_options(warnings=bad)))

    def test_bool_warnings_fails_closed(self):
        # A boolean warnings_count must not be counted as 1.
        self.assertIsNone(_volatility_from_options(_minimal_options(warnings=True)))

    def test_string_warnings_returns_none(self):
        self.assertIsNone(_volatility_from_options({"health_metrics": {"warnings_count": "x", "chains_loaded": 8}}))

    def test_non_mapping_health_metrics_returns_none(self):
        # Symmetric with _trend_from_allocation's non-mapping guard: a
        # health_metrics that is a list/scalar/string must fail closed to None,
        # never AttributeError on .get(...).
        for bad in (["not", "a", "dict"], "oops", 42, None):
            with self.subTest(health_metrics=bad):
                self.assertIsNone(_volatility_from_options({"health_metrics": bad}))

    def test_non_dict_data_returns_none(self):
        for bad in (None, [], "x", 42):
            with self.subTest(data=bad):
                self.assertIsNone(_volatility_from_options(bad))


# ---------------------------------------------------------------------------
# load_regime_input_from_snapshots
# ---------------------------------------------------------------------------

class SnapshotLoadTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _paths(
        self,
        allocation_data: object | None = None,
        options_data: object | None = None,
    ) -> dict[str, Path]:
        """Write temp snapshot files and return path dict."""
        paths: dict[str, Path] = {}
        base = Path(self.tmpdir)

        alloc_path = base / "alloc.json"
        if allocation_data is not None:
            _write_json(alloc_path, allocation_data)
        paths["NovaAllocationBot"] = alloc_path

        opts_path = base / "options.json"
        if options_data is not None:
            _write_json(opts_path, options_data)
        paths["NovaBotV2Options"] = opts_path

        return paths

    def test_valid_snapshots_return_regime_input(self):
        paths = self._paths(
            allocation_data=_minimal_allocation(90.0),
            options_data=_minimal_options(1, 8),
        )
        inputs, source = load_regime_input_from_snapshots(paths)
        self.assertIsInstance(inputs, RegimeInput)
        self.assertNotEqual(source, "synthetic_fallback")

    def test_valid_snapshots_source_label_contains_bots(self):
        paths = self._paths(
            allocation_data=_minimal_allocation(90.0),
            options_data=_minimal_options(1, 8),
        )
        _, source = load_regime_input_from_snapshots(paths)
        self.assertIn("NovaAllocationBot", source)
        self.assertIn("NovaBotV2Options", source)

    def test_missing_allocation_snapshot_falls_back(self):
        # Only options snapshot present; allocation missing → fallback
        paths = self._paths(options_data=_minimal_options(1, 8))
        inputs, source = load_regime_input_from_snapshots(paths)
        self.assertEqual(source, "synthetic_fallback")
        self.assertEqual(inputs, DRY_RUN_INPUTS)

    def test_missing_options_snapshot_falls_back(self):
        paths = self._paths(allocation_data=_minimal_allocation(90.0))
        inputs, source = load_regime_input_from_snapshots(paths)
        self.assertEqual(source, "synthetic_fallback")

    def test_both_missing_falls_back_to_synthetic(self):
        paths = self._paths()  # no files written
        inputs, source = load_regime_input_from_snapshots(paths)
        self.assertEqual(source, "synthetic_fallback")
        self.assertEqual(inputs, DRY_RUN_INPUTS)

    def test_nan_allocation_value_falls_back_to_synthetic(self):
        # A NaN allocation percentage (valid JSON to json.loads) must not become
        # a spurious strong trend; the loader falls back to synthetic.
        base = Path(self.tmpdir)
        alloc_path = base / "nan_alloc.json"
        alloc_path.write_text(
            '{"recommendation": {"recommended_allocation": {"NovaBotV2": NaN}}}',
            encoding="utf-8",
        )
        opts_path = base / "opts_ok.json"
        _write_json(opts_path, _minimal_options(1, 8))
        inputs, source = load_regime_input_from_snapshots(
            {"NovaAllocationBot": alloc_path, "NovaBotV2Options": opts_path}
        )
        self.assertEqual(source, "synthetic_fallback")
        self.assertEqual(inputs, DRY_RUN_INPUTS)

    def test_corrupt_allocation_json_falls_back(self):
        base = Path(self.tmpdir)
        alloc_path = base / "corrupt_alloc.json"
        alloc_path.write_text("{broken json", encoding="utf-8")
        opts_path = base / "options_ok.json"
        _write_json(opts_path, _minimal_options(1, 8))
        inputs, source = load_regime_input_from_snapshots(
            {"NovaAllocationBot": alloc_path, "NovaBotV2Options": opts_path}
        )
        self.assertEqual(source, "synthetic_fallback")

    def test_corrupt_options_json_falls_back(self):
        base = Path(self.tmpdir)
        alloc_path = base / "alloc_ok.json"
        _write_json(alloc_path, _minimal_allocation(90.0))
        opts_path = base / "corrupt_opts.json"
        opts_path.write_text("not-json!!", encoding="utf-8")
        inputs, source = load_regime_input_from_snapshots(
            {"NovaAllocationBot": alloc_path, "NovaBotV2Options": opts_path}
        )
        self.assertEqual(source, "synthetic_fallback")

    def test_returned_regime_input_validates(self):
        paths = self._paths(
            allocation_data=_minimal_allocation(90.0),
            options_data=_minimal_options(1, 8),
        )
        inputs, _ = load_regime_input_from_snapshots(paths)
        inputs.validate()  # must not raise

    def test_regime_cycle_status_always_safe_dry_run(self):
        from workflow.regime_cycle import run_regime_cycle
        paths = self._paths(
            allocation_data=_minimal_allocation(90.0),
            options_data=_minimal_options(1, 8),
        )
        # Inject snapshot paths via explicit inputs derived from paths
        alloc_data = json.loads((paths["NovaAllocationBot"]).read_text(encoding="utf-8"))
        opts_data = json.loads((paths["NovaBotV2Options"]).read_text(encoding="utf-8"))
        trend = _trend_from_allocation(alloc_data)
        vol = _volatility_from_options(opts_data)
        result = run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=trend, volatility_score=vol),
        )
        self.assertEqual(result["status"], "SAFE_DRY_RUN_REGIME")

    def test_no_writes_outside_market_regime_bot(self):
        """load_regime_input_from_snapshots must not write any files."""
        base = Path(self.tmpdir)
        paths = self._paths(
            allocation_data=_minimal_allocation(90.0),
            options_data=_minimal_options(1, 8),
        )
        # Baseline after input files are written, before adapter runs.
        before = set(base.rglob("*"))
        load_regime_input_from_snapshots(paths)
        after = set(base.rglob("*"))
        new_files = {p for p in (after - before) if p.is_file()}
        self.assertEqual(new_files, set(), f"Unexpected writes: {new_files}")

    def test_snapshot_adapter_imports_no_broker_modules(self):
        import core.snapshot_adapter  # noqa: F401
        forbidden = ("broker", "order", "trading")
        bad = [
            name for name in sys.modules
            if any(f in name.lower() for f in forbidden)
            and not name.startswith(("unittest", "test"))
            and "regime" not in name.lower()
        ]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
