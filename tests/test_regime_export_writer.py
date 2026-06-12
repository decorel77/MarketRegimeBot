"""Tests for utils/regime_export_writer.py — regime export schema v1."""

import json
import tempfile
import unittest
from pathlib import Path

from core.regime_contracts import RegimeDecision, RegimeSafetyState
from utils.regime_export_writer import (
    AUTHORITY_ARTIFACT,
    EXPORT_SCHEMA_VERSION,
    build_regime_export,
    build_regime_export_from_result_snapshot,
    write_regime_export,
)


def _make_decision(**kwargs) -> RegimeDecision:
    defaults = dict(
        project="MarketRegimeBot",
        status="SAFE_DRY_RUN_REGIME",
        market_regime="BULL",
        confidence=75,
        risk_level="NORMAL",
        safety=RegimeSafetyState(),
        reason=("Strong trend",),
        volatility_env="LOW_VOL",
        input_source="yfinance",
    )
    defaults.update(kwargs)
    d = RegimeDecision(**defaults)
    d.validate()
    return d


class TestBuildRegimeExport(unittest.TestCase):
    def test_schema_version_correct(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertEqual(payload["schema_version"], EXPORT_SCHEMA_VERSION)

    def test_project_is_market_regime_bot(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertEqual(payload["project"], "MarketRegimeBot")

    def test_market_regime_preserved(self):
        d = _make_decision(market_regime="BEAR", confidence=60, risk_level="HIGH",
                            volatility_env="HIGH_VOL")
        payload = build_regime_export(d)
        self.assertEqual(payload["market_regime"], "BEAR")

    def test_confidence_preserved(self):
        d = _make_decision(confidence=42)
        payload = build_regime_export(d)
        self.assertEqual(payload["confidence"], 42)

    def test_risk_level_preserved(self):
        d = _make_decision(risk_level="HIGH", market_regime="HIGH_VOLATILITY",
                            confidence=80, volatility_env="HIGH_VOL")
        payload = build_regime_export(d)
        self.assertEqual(payload["risk_level"], "HIGH")

    def test_volatility_env_preserved(self):
        d = _make_decision(volatility_env="HIGH_VOL", market_regime="HIGH_VOLATILITY",
                            confidence=80, risk_level="HIGH")
        payload = build_regime_export(d)
        self.assertEqual(payload["volatility_env"], "HIGH_VOL")

    def test_input_source_preserved(self):
        d = _make_decision(input_source="synthetic_fallback")
        payload = build_regime_export(d)
        self.assertEqual(payload["input_source"], "synthetic_fallback")

    def test_reason_is_list(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertIsInstance(payload["reason"], list)

    def test_dry_run_always_true(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertTrue(payload["dry_run"])

    def test_read_only_always_true(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertTrue(payload["read_only"])

    def test_runtime_enabled_always_false(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertFalse(payload["runtime_enabled"])

    def test_generated_at_injected(self):
        d = _make_decision()
        payload = build_regime_export(d, generated_at="2026-06-09T12:00:00Z")
        self.assertEqual(payload["generated_at"], "2026-06-09T12:00:00Z")

    def test_generated_at_defaults_to_now(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertIn("generated_at", payload)
        self.assertIsInstance(payload["generated_at"], str)

    def test_all_required_fields_present(self):
        d = _make_decision()
        payload = build_regime_export(d)
        for field in ("schema_version", "project", "generated_at", "market_regime",
                      "confidence", "risk_level", "volatility_env", "input_source",
                      "reason", "dry_run", "read_only", "runtime_enabled"):
            with self.subTest(field=field):
                self.assertIn(field, payload)

    def test_export_declares_result_snapshot_authority(self):
        d = _make_decision()
        payload = build_regime_export(d)
        self.assertEqual(payload["derived_from"], AUTHORITY_ARTIFACT)
        self.assertEqual(payload["source_schema_version"], "regime_result.v2")

    def test_export_can_be_built_from_result_snapshot_authority(self):
        d = _make_decision(market_regime="SIDEWAYS", confidence=64, risk_level="LOW")
        snapshot = d.to_dict(produced_at="2026-06-12T10:00:00+00:00")
        payload = build_regime_export_from_result_snapshot(snapshot)
        self.assertEqual(payload["generated_at"], snapshot["produced_at"])
        self.assertEqual(payload["market_regime"], snapshot["market_regime"])
        self.assertEqual(payload["confidence"], snapshot["confidence"])
        self.assertEqual(payload["risk_level"], snapshot["risk_level"])
        self.assertEqual(payload["input_source"], snapshot["input_source"])
        self.assertEqual(payload["data_is_real"], snapshot["data_is_real"])

    def test_bad_snapshot_authority_fails_closed(self):
        payload = build_regime_export_from_result_snapshot({"schema_version": "bad"})
        self.assertEqual(payload["market_regime"], "UNKNOWN")
        self.assertEqual(payload["confidence"], 0)
        self.assertFalse(payload["data_is_real"])
        self.assertEqual(payload["derived_from"], AUTHORITY_ARTIFACT)


class TestWriteRegimeExport(unittest.TestCase):
    def _export_path(self) -> Path:
        # Must be inside the MarketRegimeBot project root for the path guard
        from utils.regime_export_writer import PROJECT_ROOT
        return PROJECT_ROOT / "data" / "system" / "_test_regime_export.json"

    def test_writes_json_file(self):
        d = _make_decision()
        path = write_regime_export(d, self._export_path())
        self.assertTrue(path.exists())

    def test_written_file_parses_as_json(self):
        d = _make_decision()
        path = write_regime_export(d, self._export_path())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)

    def test_written_file_has_schema_version(self):
        d = _make_decision()
        path = write_regime_export(d, self._export_path())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], EXPORT_SCHEMA_VERSION)

    def test_refuses_to_write_outside_project(self):
        d = _make_decision()
        outside = Path(tempfile.gettempdir()) / "evil_export.json"
        with self.assertRaises(ValueError):
            write_regime_export(d, outside)

    def test_returns_path(self):
        d = _make_decision()
        ep = self._export_path()
        result = write_regime_export(d, ep)
        self.assertEqual(result, ep)


class TestNoBrokerImports(unittest.TestCase):
    def test_no_broker_imports(self):
        import ast
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "utils" / "regime_export_writer.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(imports & broker_modules)


if __name__ == "__main__":
    unittest.main()
