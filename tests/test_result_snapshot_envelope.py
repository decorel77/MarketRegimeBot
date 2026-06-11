"""QA-001: timestamped result snapshot envelope.

Guards the freshness envelope on every serialized RegimeDecision:

  - ``produced_at``      UTC ISO-8601, injectable for deterministic tests
  - ``fresh_until``      produced_at + 24h
  - ``schema_version``   "regime_result.v2"
  - ``producer_id``      "MarketRegimeBot"

Also guards the v1 → v2 regression contract: every key the previous schema
carried must still be present (additive change only).
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from core.regime_classifier import RegimeInput
from core.regime_contracts import (
    FRESHNESS_WINDOW,
    PRODUCER_ID,
    RESULT_SCHEMA_VERSION,
    RegimeValidationError,
    build_snapshot_envelope,
    build_unknown_regime_decision,
)
from workflow import regime_cycle


# Every key the pre-QA-001 (v1) result snapshot carried. The envelope is
# additive: removing or renaming any of these is a breaking schema change.
V1_SNAPSHOT_KEYS = (
    "project",
    "status",
    "market_regime",
    "confidence",
    "risk_level",
    "reason",
    "volatility_env",
    "input_source",
    "data_is_real",
    "dry_run",
    "broker_execution_enabled",
    "order_placement_enabled",
    "live_trading_enabled",
    "money_movement_enabled",
    "writes_to_other_projects_enabled",
    "allocation_export_enabled",
)

ENVELOPE_KEYS = ("produced_at", "fresh_until", "schema_version", "producer_id")


class EnvelopeBuilderTests(unittest.TestCase):
    def test_injected_produced_at_preserved(self):
        env = build_snapshot_envelope("2026-06-11T12:00:00+00:00")
        self.assertEqual(env["produced_at"], "2026-06-11T12:00:00+00:00")

    def test_fresh_until_is_produced_at_plus_24h(self):
        env = build_snapshot_envelope("2026-06-11T12:00:00+00:00")
        produced = datetime.fromisoformat(env["produced_at"])
        fresh = datetime.fromisoformat(env["fresh_until"])
        self.assertEqual(fresh - produced, timedelta(hours=24))
        self.assertEqual(FRESHNESS_WINDOW, timedelta(hours=24))

    def test_schema_version_v2(self):
        env = build_snapshot_envelope()
        self.assertEqual(env["schema_version"], "regime_result.v2")
        self.assertEqual(RESULT_SCHEMA_VERSION, "regime_result.v2")

    def test_producer_id(self):
        env = build_snapshot_envelope()
        self.assertEqual(env["producer_id"], "MarketRegimeBot")
        self.assertEqual(PRODUCER_ID, "MarketRegimeBot")

    def test_default_produced_at_is_recent_utc(self):
        before = datetime.now(timezone.utc)
        env = build_snapshot_envelope()
        after = datetime.now(timezone.utc)
        produced = datetime.fromisoformat(env["produced_at"])
        self.assertIsNotNone(produced.tzinfo)
        self.assertLessEqual(before, produced)
        self.assertLessEqual(produced, after)

    def test_zulu_suffix_accepted(self):
        env = build_snapshot_envelope("2026-06-11T12:00:00Z")
        produced = datetime.fromisoformat(env["produced_at"])
        self.assertEqual(produced, datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc))

    def test_naive_timestamp_assumed_utc(self):
        env = build_snapshot_envelope("2026-06-11T12:00:00")
        produced = datetime.fromisoformat(env["produced_at"])
        self.assertEqual(produced, datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc))

    def test_non_utc_offset_normalised_to_utc(self):
        env = build_snapshot_envelope("2026-06-11T14:00:00+02:00")
        produced = datetime.fromisoformat(env["produced_at"])
        self.assertEqual(produced, datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc))

    def test_unparseable_produced_at_rejected(self):
        for bad in ("not-a-timestamp", "", "11/06/2026"):
            with self.subTest(bad=bad):
                with self.assertRaises(RegimeValidationError):
                    build_snapshot_envelope(bad)


class DecisionDictEnvelopeTests(unittest.TestCase):
    def test_to_dict_contains_envelope(self):
        payload = build_unknown_regime_decision().to_dict()
        for key in ENVELOPE_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_to_dict_injectable_produced_at(self):
        payload = build_unknown_regime_decision().to_dict(
            produced_at="2026-06-11T12:00:00+00:00"
        )
        self.assertEqual(payload["produced_at"], "2026-06-11T12:00:00+00:00")
        self.assertEqual(payload["fresh_until"], "2026-06-12T12:00:00+00:00")

    def test_regression_all_v1_keys_still_present(self):
        payload = build_unknown_regime_decision().to_dict()
        for key in V1_SNAPSHOT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, payload)


class SnapshotFileEnvelopeTests(unittest.TestCase):
    def _temp_snapshot_path(self):
        # Inside the project root (the write guard refuses anything outside);
        # removed after the test so no artifact is left behind.
        path = (
            regime_cycle.PROJECT_ROOT
            / "data"
            / "system"
            / "_test_result_snapshot_envelope.json"
        )
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_written_snapshot_carries_envelope(self):
        path = self._temp_snapshot_path()
        regime_cycle.write_result_snapshot(
            build_unknown_regime_decision(),
            path,
            produced_at="2026-06-11T12:00:00+00:00",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["produced_at"], "2026-06-11T12:00:00+00:00")
        self.assertEqual(payload["fresh_until"], "2026-06-12T12:00:00+00:00")
        self.assertEqual(payload["schema_version"], RESULT_SCHEMA_VERSION)
        self.assertEqual(payload["producer_id"], PRODUCER_ID)

    def test_written_snapshot_keeps_v1_keys(self):
        path = self._temp_snapshot_path()
        regime_cycle.write_result_snapshot(build_unknown_regime_decision(), path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key in V1_SNAPSHOT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, payload)


class CycleEnvelopeThreadingTests(unittest.TestCase):
    def test_cycle_threads_injected_produced_at_into_decision(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
            produced_at="2026-06-11T12:00:00+00:00",
        )
        self.assertEqual(result["decision"]["produced_at"], "2026-06-11T12:00:00+00:00")
        self.assertEqual(result["decision"]["fresh_until"], "2026-06-12T12:00:00+00:00")

    def test_cycle_default_produced_at_is_parseable_utc(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
        )
        produced = datetime.fromisoformat(result["decision"]["produced_at"])
        self.assertIsNotNone(produced.tzinfo)

    def test_cycle_decision_keeps_v1_keys(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
        )
        for key in V1_SNAPSHOT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, result["decision"])


if __name__ == "__main__":
    unittest.main()
