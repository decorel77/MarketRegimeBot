"""REGIME-PHASE-004 synthetic tests for core/risk_classifier.py.

Synthetic fixtures only (tests/fixtures/*.json); offline; deterministic
(freshness uses an injected ``now``). Mirrors the existing classifier test
style and the broker-free assertions in test_startup_guardrails / fallback
tests. No live market read, no network, no data/system or data/history access.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from core import risk_classifier as rc
from core.risk_classifier import classify_risk
from core.regime_contracts import FRESHNESS_WINDOW

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODULE_FILE = Path(rc.__file__)

# Deterministic evaluation clock: 2026-06-15 12:00 UTC. Fresh fixtures are
# produced shortly before this; the stale fixture is days older.
NOW = "2026-06-15T12:00:00+00:00"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class HappyPaths(unittest.TestCase):
    def test_risk_on_clear(self):
        r = classify_risk(load("risk_on_clear"), now=NOW)
        self.assertEqual(r.label, "RISK_ON")
        self.assertEqual(r.status, "OK")
        self.assertEqual(r.confidence, 0.85)
        self.assertTrue(r.data_is_real)

    def test_risk_off_clear(self):
        r = classify_risk(load("risk_off_clear"), now=NOW)
        self.assertEqual(r.label, "RISK_OFF")
        self.assertEqual(r.status, "OK")
        self.assertIsInstance(r.confidence, float)
        self.assertTrue(r.data_is_real)


class Ambiguity(unittest.TestCase):
    def test_ambiguous_is_insufficient_with_confidence_withheld(self):
        r = classify_risk(load("ambiguous"), now=NOW)
        self.assertEqual(r.label, "UNKNOWN")
        self.assertEqual(r.status, "INSUFFICIENT")
        self.assertIsNone(r.confidence)


class FailClosedInputs(unittest.TestCase):
    def test_missing_inputs(self):
        r = classify_risk(load("missing_inputs"), now=NOW)
        self.assertEqual((r.label, r.status), ("UNKNOWN", "MISSING"))
        self.assertFalse(r.data_is_real)

    def test_invalid_inputs(self):
        r = classify_risk(load("invalid_inputs"), now=NOW)
        self.assertEqual((r.label, r.status), ("UNKNOWN", "INVALID"))
        self.assertFalse(r.data_is_real)

    def test_none_and_garbage_do_not_raise(self):
        for bad in (None, [], "x", 42):
            r = classify_risk(bad, now=NOW)  # type: ignore[arg-type]
            self.assertEqual(r.label, "UNKNOWN")
            self.assertEqual(r.status, "MISSING")


class Freshness(unittest.TestCase):
    def test_stale_fixture_is_non_actionable(self):
        r = classify_risk(load("stale"), now=NOW)
        self.assertEqual((r.label, r.status), ("UNKNOWN", "STALE"))
        self.assertIsNone(r.confidence)

    def test_fresh_flag_true_but_window_expired_is_stale(self):
        sig = load("risk_on_clear")
        sig["is_fresh"] = True
        # produced_at more than FRESHNESS_WINDOW before NOW
        from datetime import datetime, timezone
        old = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc) - FRESHNESS_WINDOW
        sig["produced_at"] = (old.isoformat())
        r = classify_risk(sig, now=NOW)
        self.assertEqual(r.status, "STALE")

    def test_is_fresh_false_is_stale_even_with_recent_produced_at(self):
        sig = load("risk_on_clear")
        sig["is_fresh"] = False
        r = classify_risk(sig, now=NOW)
        self.assertEqual(r.status, "STALE")


class Realness(unittest.TestCase):
    def test_not_real_is_never_trusted(self):
        r = classify_risk(load("not_real"), now=NOW)
        self.assertEqual((r.label, r.status), ("UNKNOWN", "NOT_REAL"))
        self.assertFalse(r.data_is_real)

    def test_mixed_provenance_fails_closed_to_untrusted(self):
        r = classify_risk(load("mixed_provenance"), now=NOW)
        self.assertFalse(r.data_is_real)
        self.assertEqual(r.status, "NOT_REAL")

    def test_data_is_real_false_is_never_promoted(self):
        # Even with an otherwise textbook RISK_ON setup, a non-real source can
        # never reach RISK_ON / OK.
        sig = load("risk_on_clear")
        sig["data_is_real"] = False
        r = classify_risk(sig, now=NOW)
        self.assertEqual(r.label, "UNKNOWN")
        self.assertFalse(r.data_is_real)


class Determinism(unittest.TestCase):
    def test_same_fixture_same_result(self):
        for name in ("risk_on_clear", "risk_off_clear", "ambiguous", "stale", "not_real"):
            a = classify_risk(load(name), now=NOW).to_dict()
            b = classify_risk(load(name), now=NOW).to_dict()
            self.assertEqual(a, b, name)


class NoTradingAuthority(unittest.TestCase):
    ALLOWED_KEYS = {"label", "status", "confidence", "data_is_real", "notes", "schema_version"}
    FORBIDDEN_FRAGMENTS = (
        "order", "allocat", "position", "size", "capital", "risk_pct", "weight",
        "execute", "execution", "broker", "buy", "sell", "money", "cash",
    )

    def test_output_keys_are_advisory_only(self):
        out = classify_risk(load("risk_on_clear"), now=NOW).to_dict()
        self.assertEqual(set(out), self.ALLOWED_KEYS)

    def test_no_trading_wording_in_any_output(self):
        for name in ("risk_on_clear", "risk_off_clear", "ambiguous", "missing_inputs",
                     "invalid_inputs", "stale", "not_real", "mixed_provenance"):
            blob = json.dumps(classify_risk(load(name), now=NOW).to_dict()).lower()
            for frag in self.FORBIDDEN_FRAGMENTS:
                self.assertNotIn(frag, blob, f"{name} output contains forbidden fragment {frag!r}")


class BrokerFreeOffline(unittest.TestCase):
    FORBIDDEN_IMPORTS = (
        "yfinance", "requests", "urllib", "socket", "http", "http.client",
        "ib_insync", "ibapi", "alpaca", "alpaca_trade_api", "robin_stocks",
        "ccxt", "tastytrade",
    )

    def test_module_imports_nothing_networked_or_broker(self):
        tree = ast.parse(MODULE_FILE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for name in imported:
            top = name.split(".")[0]
            self.assertNotIn(top, self.FORBIDDEN_IMPORTS, f"forbidden import {name!r}")

    def test_module_performs_no_file_io(self):
        # Pure module: prove it makes no file-read/-write call (regardless of what
        # the safety docstring mentions). Inspect call names via the AST.
        tree = ast.parse(MODULE_FILE.read_text(encoding="utf-8"))
        io_calls = {"open", "read_text", "write_text", "read_bytes", "write_bytes", "load", "loads"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                self.assertNotIn(name, io_calls, f"module performs I/O via {name!r}")

    def test_all_fixtures_are_marked_synthetic(self):
        for fx in FIXTURES.glob("*.json"):
            data = json.loads(fx.read_text(encoding="utf-8"))
            if "regime" in data:  # risk-classifier fixtures
                self.assertTrue(data.get("_synthetic"), f"{fx.name} not marked synthetic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
