"""
Tests for data/system/regime_registry.json and its validator.

Covers:
- Valid schema passes validation
- Missing required fields are caught
- Invalid types are caught
- runtime_effect is always false
- execution_authority is always false
- informational_only is always true
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from utils.regime_registry_validator import validate

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "system" / "regime_registry.json"


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


class TestRegistryFileExists(unittest.TestCase):
    def test_registry_file_exists(self):
        self.assertTrue(REGISTRY_PATH.exists(), f"Registry not found: {REGISTRY_PATH}")

    def test_registry_is_valid_json(self):
        data = load_registry()
        self.assertIsInstance(data, dict)


class TestValidSchemaPassesValidation(unittest.TestCase):
    def test_valid_registry_produces_no_errors(self):
        errors = validate(REGISTRY_PATH)
        self.assertEqual(
            errors, [],
            f"Expected no validation errors but got:\n" + "\n".join(errors),
        )


class TestTopLevelRequiredKeys(unittest.TestCase):
    def _validate_without_key(self, key: str) -> list[str]:
        data = load_registry()
        del data[key]
        path = write_temp(data)
        return validate(path)

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
        path = write_temp(data)
        errors = validate(path)
        self.assertTrue(any("execution_authority" in e and "must be false" in e for e in errors))

    def test_safety_missing_field_caught(self):
        data = load_registry()
        del data["_safety"]["broker_authority"]
        path = write_temp(data)
        errors = validate(path)
        self.assertTrue(any("broker_authority" in e for e in errors))


class TestRegimeEntries(unittest.TestCase):
    def setUp(self):
        self.data = load_registry()
        self.regimes = self.data["regimes"]

    def test_regimes_is_non_empty_list(self):
        self.assertIsInstance(self.regimes, list)
        self.assertGreater(len(self.regimes), 0)

    def test_all_regimes_have_required_fields(self):
        required = {"id", "label", "enabled", "description", "informational_only", "runtime_effect", "execution_authority"}
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


class TestInvalidTypesCaught(unittest.TestCase):
    def _tamper_regime(self, field: str, value) -> list[str]:
        data = load_registry()
        data["regimes"][0][field] = value
        path = write_temp(data)
        return validate(path)

    def test_enabled_wrong_type_caught(self):
        errors = self._tamper_regime("enabled", "yes")
        self.assertTrue(any("enabled" in e for e in errors))

    def test_label_wrong_type_caught(self):
        errors = self._tamper_regime("label", 42)
        self.assertTrue(any("label" in e for e in errors))

    def test_runtime_effect_true_caught(self):
        errors = self._tamper_regime("runtime_effect", True)
        self.assertTrue(
            any("runtime_effect" in e and "must be false" in e for e in errors)
        )

    def test_execution_authority_true_caught(self):
        errors = self._tamper_regime("execution_authority", True)
        self.assertTrue(
            any("execution_authority" in e and "must be false" in e for e in errors)
        )

    def test_informational_only_false_caught(self):
        errors = self._tamper_regime("informational_only", False)
        self.assertTrue(
            any("informational_only" in e and "must be true" in e for e in errors)
        )


class TestMissingRegimeFields(unittest.TestCase):
    def _drop_regime_field(self, field: str) -> list[str]:
        data = load_registry()
        del data["regimes"][0][field]
        path = write_temp(data)
        return validate(path)

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
