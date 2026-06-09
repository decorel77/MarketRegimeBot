"""
Tests for data/system/regime_registry.json and its validator.

Covers:
- Valid schema passes validation
- Missing required fields are caught
- Invalid types are caught
- runtime_effect is always false
- execution_authority is always false
- informational_only is always true
- Schema version is 1.1.0
- v1.1.0 fields: classifier_id, classifier_aligned, scoring_hints, signals
- Naming alignment documentation: known mismatches are recorded correctly
- Unsupported schema version is caught
"""

import json
import tempfile
import unittest
from pathlib import Path

from utils.regime_registry_validator import validate

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "system" / "regime_registry.json"

# Regimes where registry ID != classifier ID (the known mismatch)
KNOWN_MISALIGNED = {
    "BULL_MARKET":    "BULL",
    "BEAR_MARKET":    "BEAR",
    "SIDEWAYS_MARKET":"SIDEWAYS",
}

# Regimes where classifier is not yet implemented
CLASSIFIER_NOT_IMPLEMENTED = {"LOW_VOLATILITY", "RISK_ON", "RISK_OFF"}

# Regimes where IDs are already aligned
CLASSIFIER_ALIGNED = {"HIGH_VOLATILITY"}


def load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def write_temp(data: dict) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp)
    tmp.flush()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

class TestRegistryFileExists(unittest.TestCase):
    def test_registry_file_exists(self):
        self.assertTrue(REGISTRY_PATH.exists(), f"Registry not found: {REGISTRY_PATH}")

    def test_registry_is_valid_json(self):
        data = load_registry()
        self.assertIsInstance(data, dict)


# ---------------------------------------------------------------------------
# Valid schema passes
# ---------------------------------------------------------------------------

class TestValidSchemaPassesValidation(unittest.TestCase):
    def test_valid_registry_produces_no_errors(self):
        errors = validate(REGISTRY_PATH)
        self.assertEqual(
            errors, [],
            "Expected no validation errors but got:\n" + "\n".join(errors),
        )


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion(unittest.TestCase):
    def test_schema_version_is_1_1_0(self):
        data = load_registry()
        self.assertEqual(data["_schema_version"], "1.1.0")

    def test_unsupported_schema_version_caught(self):
        data = load_registry()
        data["_schema_version"] = "99.0.0"
        errors = validate(write_temp(data))
        self.assertTrue(any("Unsupported" in e and "schema_version" in e for e in errors))


# ---------------------------------------------------------------------------
# Top-level required keys
# ---------------------------------------------------------------------------

class TestTopLevelRequiredKeys(unittest.TestCase):
    def _validate_without_key(self, key: str) -> list[str]:
        data = load_registry()
        del data[key]
        return validate(write_temp(data))

    def test_missing_schema_version(self):
        errors = self._validate_without_key("_schema_version")
        self.assertTrue(any("_schema_version" in e for e in errors))

    def test_missing_description(self):
        errors = self._validate_without_key("_description")
        self.assertTrue(any("_description" in e for e in errors))

    def test_missing_safety(self):
        errors = self._validate_without_key("_safety")
        self.assertTrue(any("_safety" in e for e in errors))

    def test_missing_regimes(self):
        errors = self._validate_without_key("regimes")
        self.assertTrue(any("regimes" in e for e in errors))


# ---------------------------------------------------------------------------
# Safety block
# ---------------------------------------------------------------------------

class TestSafetyBlock(unittest.TestCase):
    def test_execution_authority_is_false_in_safety(self):
        data = load_registry()
        self.assertFalse(data["_safety"]["execution_authority"])

    def test_broker_authority_is_false_in_safety(self):
        data = load_registry()
        self.assertFalse(data["_safety"]["broker_authority"])

    def test_order_authority_is_false_in_safety(self):
        data = load_registry()
        self.assertFalse(data["_safety"]["order_authority"])

    def test_runtime_effect_is_false_in_safety(self):
        data = load_registry()
        self.assertFalse(data["_safety"]["runtime_effect"])

    def test_safety_true_execution_authority_caught(self):
        data = load_registry()
        data["_safety"]["execution_authority"] = True
        errors = validate(write_temp(data))
        self.assertTrue(any("execution_authority" in e and "must be false" in e for e in errors))

    def test_safety_missing_field_caught(self):
        data = load_registry()
        del data["_safety"]["broker_authority"]
        errors = validate(write_temp(data))
        self.assertTrue(any("broker_authority" in e for e in errors))


# ---------------------------------------------------------------------------
# Core regime entries
# ---------------------------------------------------------------------------

class TestRegimeEntries(unittest.TestCase):
    def setUp(self):
        self.data = load_registry()
        self.regimes = self.data["regimes"]

    def test_regimes_is_non_empty_list(self):
        self.assertIsInstance(self.regimes, list)
        self.assertGreater(len(self.regimes), 0)

    def test_all_regimes_have_required_fields(self):
        required = {
            "id", "label", "enabled", "description",
            "informational_only", "runtime_effect", "execution_authority",
        }
        for regime in self.regimes:
            with self.subTest(regime_id=regime.get("id")):
                missing = required - set(regime.keys())
                self.assertEqual(missing, set(), f"Missing fields: {missing}")

    def test_all_regimes_runtime_effect_is_false(self):
        for regime in self.regimes:
            with self.subTest(regime_id=regime.get("id")):
                self.assertFalse(
                    regime["runtime_effect"],
                    f"regime {regime['id']}: runtime_effect must be false",
                )

    def test_all_regimes_execution_authority_is_false(self):
        for regime in self.regimes:
            with self.subTest(regime_id=regime.get("id")):
                self.assertFalse(
                    regime["execution_authority"],
                    f"regime {regime['id']}: execution_authority must be false",
                )

    def test_all_regimes_informational_only_is_true(self):
        for regime in self.regimes:
            with self.subTest(regime_id=regime.get("id")):
                self.assertTrue(
                    regime["informational_only"],
                    f"regime {regime['id']}: informational_only must be true",
                )

    def test_all_regimes_enabled_is_bool(self):
        for regime in self.regimes:
            with self.subTest(regime_id=regime.get("id")):
                self.assertIsInstance(regime["enabled"], bool)

    def test_all_regime_ids_are_unique(self):
        ids = [r["id"] for r in self.regimes]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate regime IDs found")

    def test_expected_regimes_present(self):
        ids = {r["id"] for r in self.regimes}
        expected = {
            "BULL_MARKET", "BEAR_MARKET", "SIDEWAYS_MARKET",
            "HIGH_VOLATILITY", "LOW_VOLATILITY", "RISK_ON", "RISK_OFF",
        }
        self.assertEqual(ids, expected)


# ---------------------------------------------------------------------------
# v1.1.0 — classifier_id and naming alignment
# ---------------------------------------------------------------------------

class TestClassifierIdField(unittest.TestCase):
    def setUp(self):
        self.regimes = {r["id"]: r for r in load_registry()["regimes"]}

    def test_all_regimes_have_classifier_id_field(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                self.assertIn("classifier_id", regime)

    def test_known_misaligned_regimes_have_correct_classifier_id(self):
        """BULL_MARKET, BEAR_MARKET, SIDEWAYS_MARKET must document their short classifier IDs."""
        for registry_id, expected_classifier_id in KNOWN_MISALIGNED.items():
            with self.subTest(registry_id=registry_id):
                regime = self.regimes[registry_id]
                self.assertEqual(
                    regime["classifier_id"],
                    expected_classifier_id,
                    f"{registry_id} should document classifier_id={expected_classifier_id!r}",
                )

    def test_known_misaligned_regimes_not_marked_aligned(self):
        """Misaligned regimes must have classifier_aligned=False."""
        for registry_id in KNOWN_MISALIGNED:
            with self.subTest(registry_id=registry_id):
                regime = self.regimes[registry_id]
                self.assertFalse(
                    regime.get("classifier_aligned"),
                    f"{registry_id} must have classifier_aligned=false (mismatch documented)",
                )

    def test_high_volatility_is_aligned(self):
        """HIGH_VOLATILITY registry ID and classifier ID match — must be marked aligned."""
        regime = self.regimes["HIGH_VOLATILITY"]
        self.assertEqual(regime["classifier_id"], "HIGH_VOLATILITY")
        self.assertTrue(regime["classifier_aligned"])

    def test_unimplemented_regimes_have_null_classifier_id(self):
        """Regimes not yet in classifier must have classifier_id=null."""
        for regime_id in CLASSIFIER_NOT_IMPLEMENTED:
            with self.subTest(regime_id=regime_id):
                regime = self.regimes[regime_id]
                self.assertIsNone(
                    regime["classifier_id"],
                    f"{regime_id} is not yet in classifier — classifier_id must be null",
                )

    def test_classifier_id_is_string_or_null(self):
        """classifier_id must be a string or null — never an integer or boolean."""
        for regime in self.regimes.values():
            with self.subTest(regime_id=regime["id"]):
                cid = regime.get("classifier_id", "MISSING")
                self.assertNotEqual(cid, "MISSING", "classifier_id field missing")
                self.assertIn(
                    type(cid), (str, type(None)),
                    f"classifier_id must be str or None, got {type(cid)}",
                )

    def test_classifier_id_wrong_type_caught_by_validator(self):
        data = load_registry()
        data["regimes"][0]["classifier_id"] = 999
        errors = validate(write_temp(data))
        self.assertTrue(any("classifier_id" in e for e in errors))


# ---------------------------------------------------------------------------
# v1.1.0 — scoring_hints
# ---------------------------------------------------------------------------

class TestScoringHints(unittest.TestCase):
    def setUp(self):
        self.regimes = {r["id"]: r for r in load_registry()["regimes"]}

    def test_all_regimes_have_scoring_hints(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                self.assertIn("scoring_hints", regime)

    def test_scoring_hints_is_dict(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                self.assertIsInstance(regime["scoring_hints"], dict)

    def test_scoring_hints_has_required_fields(self):
        required = {"source", "priority", "conditions", "confidence_formula", "risk_level_rule"}
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                hints = regime["scoring_hints"]
                missing = required - set(hints.keys())
                self.assertEqual(missing, set(), f"{regime_id} scoring_hints missing: {missing}")

    def test_implemented_regimes_have_integer_priority(self):
        """Regimes implemented in the classifier must have a numeric priority."""
        implemented = {"BULL_MARKET", "BEAR_MARKET", "SIDEWAYS_MARKET", "HIGH_VOLATILITY"}
        for regime_id in implemented:
            with self.subTest(regime_id=regime_id):
                priority = self.regimes[regime_id]["scoring_hints"]["priority"]
                self.assertIsInstance(priority, int)

    def test_high_volatility_has_priority_1(self):
        """HIGH_VOLATILITY is evaluated first — must have priority 1."""
        priority = self.regimes["HIGH_VOLATILITY"]["scoring_hints"]["priority"]
        self.assertEqual(priority, 1)

    def test_scoring_hints_conditions_is_list(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                self.assertIsInstance(regime["scoring_hints"]["conditions"], list)

    def test_invalid_scoring_hints_type_caught(self):
        data = load_registry()
        data["regimes"][0]["scoring_hints"] = "not-an-object"
        errors = validate(write_temp(data))
        self.assertTrue(any("scoring_hints" in e for e in errors))

    def test_scoring_hints_condition_missing_field_caught(self):
        data = load_registry()
        # Remove required 'value' field from first condition of BULL_MARKET
        bull = next(r for r in data["regimes"] if r["id"] == "BULL_MARKET")
        if bull["scoring_hints"]["conditions"]:
            del bull["scoring_hints"]["conditions"][0]["value"]
        errors = validate(write_temp(data))
        self.assertTrue(any("conditions" in e for e in errors))


# ---------------------------------------------------------------------------
# v1.1.0 — signals
# ---------------------------------------------------------------------------

class TestSignals(unittest.TestCase):
    def setUp(self):
        self.regimes = {r["id"]: r for r in load_registry()["regimes"]}

    def test_all_regimes_have_signals(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                self.assertIn("signals", regime)

    def test_signals_is_non_empty_list(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                sigs = regime["signals"]
                self.assertIsInstance(sigs, list)
                self.assertGreater(len(sigs), 0, f"{regime_id}: signals list must not be empty")

    def test_all_signals_are_strings(self):
        for regime_id, regime in self.regimes.items():
            with self.subTest(regime_id=regime_id):
                for i, sig in enumerate(regime["signals"]):
                    self.assertIsInstance(sig, str, f"{regime_id} signals[{i}] must be a string")

    def test_invalid_signals_type_caught(self):
        data = load_registry()
        data["regimes"][0]["signals"] = "not-a-list"
        errors = validate(write_temp(data))
        self.assertTrue(any("signals" in e for e in errors))

    def test_non_string_signal_caught(self):
        data = load_registry()
        data["regimes"][0]["signals"] = [42]
        errors = validate(write_temp(data))
        self.assertTrue(any("signals" in e for e in errors))


# ---------------------------------------------------------------------------
# v1.1.0 — naming alignment metadata block
# ---------------------------------------------------------------------------

class TestNamingAlignmentBlock(unittest.TestCase):
    def setUp(self):
        self.data = load_registry()

    def test_naming_alignment_block_exists(self):
        self.assertIn("_naming_alignment", self.data)

    def test_naming_alignment_has_misaligned_pairs(self):
        pairs = self.data["_naming_alignment"]["misaligned_pairs"]
        self.assertIsInstance(pairs, list)
        self.assertGreater(len(pairs), 0)

    def test_all_known_mismatches_documented_in_block(self):
        pairs = self.data["_naming_alignment"]["misaligned_pairs"]
        documented_registry_ids = {p["registry_id"] for p in pairs}
        for registry_id in KNOWN_MISALIGNED:
            with self.subTest(registry_id=registry_id):
                self.assertIn(
                    registry_id, documented_registry_ids,
                    f"{registry_id} naming mismatch must be documented in _naming_alignment",
                )

    def test_misaligned_pair_entries_have_required_fields(self):
        pairs = self.data["_naming_alignment"]["misaligned_pairs"]
        required = {"registry_id", "classifier_id", "resolution"}
        for pair in pairs:
            with self.subTest(registry_id=pair.get("registry_id")):
                missing = required - set(pair.keys())
                self.assertEqual(missing, set(), f"Pair missing fields: {missing}")

    def test_misaligned_pairs_match_classifier_id_fields(self):
        """_naming_alignment.misaligned_pairs must be consistent with regime classifier_id fields."""
        pairs = {p["registry_id"]: p["classifier_id"]
                 for p in self.data["_naming_alignment"]["misaligned_pairs"]}
        regimes = {r["id"]: r for r in self.data["regimes"]}
        for registry_id, documented_classifier_id in pairs.items():
            with self.subTest(registry_id=registry_id):
                actual_classifier_id = regimes[registry_id]["classifier_id"]
                self.assertEqual(
                    actual_classifier_id,
                    documented_classifier_id,
                    f"_naming_alignment entry for {registry_id} says classifier_id="
                    f"{documented_classifier_id!r} but regime.classifier_id={actual_classifier_id!r}",
                )


# ---------------------------------------------------------------------------
# Invalid types caught
# ---------------------------------------------------------------------------

class TestInvalidTypesCaught(unittest.TestCase):
    def _tamper_regime(self, field: str, value) -> list[str]:
        data = load_registry()
        data["regimes"][0][field] = value
        return validate(write_temp(data))

    def test_enabled_wrong_type_caught(self):
        errors = self._tamper_regime("enabled", "yes")
        self.assertTrue(any("enabled" in e for e in errors))

    def test_label_wrong_type_caught(self):
        errors = self._tamper_regime("label", 42)
        self.assertTrue(any("label" in e for e in errors))

    def test_runtime_effect_true_caught(self):
        errors = self._tamper_regime("runtime_effect", True)
        self.assertTrue(any("runtime_effect" in e and "must be false" in e for e in errors))

    def test_execution_authority_true_caught(self):
        errors = self._tamper_regime("execution_authority", True)
        self.assertTrue(any("execution_authority" in e and "must be false" in e for e in errors))

    def test_informational_only_false_caught(self):
        errors = self._tamper_regime("informational_only", False)
        self.assertTrue(any("informational_only" in e and "must be true" in e for e in errors))


# ---------------------------------------------------------------------------
# Missing regime fields
# ---------------------------------------------------------------------------

class TestMissingRegimeFields(unittest.TestCase):
    def _drop_regime_field(self, field: str) -> list[str]:
        data = load_registry()
        del data["regimes"][0][field]
        return validate(write_temp(data))

    def test_missing_id_caught(self):
        errors = self._drop_regime_field("id")
        self.assertTrue(any("id" in e for e in errors))

    def test_missing_runtime_effect_caught(self):
        errors = self._drop_regime_field("runtime_effect")
        self.assertTrue(any("runtime_effect" in e for e in errors))

    def test_missing_execution_authority_caught(self):
        errors = self._drop_regime_field("execution_authority")
        self.assertTrue(any("execution_authority" in e for e in errors))

    def test_missing_informational_only_caught(self):
        errors = self._drop_regime_field("informational_only")
        self.assertTrue(any("informational_only" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
