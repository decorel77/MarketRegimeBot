"""
Tests for data/system/autocycle_policy.json and its validator.

Covers:
- Valid schema passes validation
- execution_allowed remains false
- runtime_effect remains false
- enabled remains false
- max_tasks_per_cycle == 3
- commit_requires_human_approval remains true
- push_requires_human_approval remains true
- allowed_risk_levels is ["LOW"] only
- prohibited task types include BROKER, EXECUTION, TRADING, ORDER
- missing fields are caught
- invalid values are caught
"""

import json
import tempfile
import unittest
from pathlib import Path

from utils.autocycle_policy_validator import validate

POLICY_PATH = Path(__file__).parent.parent / "data" / "system" / "autocycle_policy.json"


def load_policy() -> dict:
    with open(POLICY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def write_temp(data: dict) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp)
    tmp.flush()
    return Path(tmp.name)


class TestPolicyFileExists(unittest.TestCase):
    def test_policy_file_exists(self):
        self.assertTrue(POLICY_PATH.exists(), f"Policy not found: {POLICY_PATH}")

    def test_policy_is_valid_json(self):
        data = load_policy()
        self.assertIsInstance(data, dict)


class TestValidSchemaPasses(unittest.TestCase):
    def test_valid_policy_produces_no_errors(self):
        errors = validate(POLICY_PATH)
        self.assertEqual(
            errors, [],
            "Expected no validation errors but got:\n" + "\n".join(errors),
        )


class TestExecutionRemainsFalse(unittest.TestCase):
    """execution_allowed must be false in both _safety and policy blocks."""

    def test_safety_execution_allowed_is_false(self):
        data = load_policy()
        self.assertFalse(data["_safety"]["execution_allowed"])

    def test_policy_execution_allowed_is_false(self):
        data = load_policy()
        self.assertFalse(data["policy"]["execution_allowed"])

    def test_safety_execution_allowed_true_caught(self):
        data = load_policy()
        data["_safety"]["execution_allowed"] = True
        errors = validate(write_temp(data))
        self.assertTrue(
            any("execution_allowed" in e and "must be false" in e for e in errors)
        )

    def test_policy_execution_allowed_true_caught(self):
        data = load_policy()
        data["policy"]["execution_allowed"] = True
        errors = validate(write_temp(data))
        self.assertTrue(
            any("execution_allowed" in e and "must be false" in e for e in errors)
        )


class TestRuntimeEffectRemainsFalse(unittest.TestCase):
    def test_safety_runtime_effect_is_false(self):
        data = load_policy()
        self.assertFalse(data["_safety"]["runtime_effect"])

    def test_policy_runtime_effect_is_false(self):
        data = load_policy()
        self.assertFalse(data["policy"]["runtime_effect"])

    def test_safety_runtime_effect_true_caught(self):
        data = load_policy()
        data["_safety"]["runtime_effect"] = True
        errors = validate(write_temp(data))
        self.assertTrue(
            any("runtime_effect" in e and "must be false" in e for e in errors)
        )

    def test_policy_runtime_effect_true_caught(self):
        data = load_policy()
        data["policy"]["runtime_effect"] = True
        errors = validate(write_temp(data))
        self.assertTrue(
            any("runtime_effect" in e and "must be false" in e for e in errors)
        )


class TestEnabledRemainsFalse(unittest.TestCase):
    def test_policy_enabled_is_false(self):
        data = load_policy()
        self.assertFalse(data["policy"]["enabled"])

    def test_policy_enabled_true_caught(self):
        data = load_policy()
        data["policy"]["enabled"] = True
        errors = validate(write_temp(data))
        self.assertTrue(
            any("enabled" in e and "must be false" in e for e in errors)
        )


class TestMaxTasksPerCycle(unittest.TestCase):
    def test_max_tasks_per_cycle_is_3(self):
        data = load_policy()
        self.assertEqual(data["policy"]["max_tasks_per_cycle"], 3)

    def test_max_tasks_per_cycle_wrong_value_caught(self):
        data = load_policy()
        data["policy"]["max_tasks_per_cycle"] = 10
        errors = validate(write_temp(data))
        self.assertTrue(any("max_tasks_per_cycle" in e for e in errors))

    def test_max_tasks_per_cycle_wrong_type_caught(self):
        data = load_policy()
        data["policy"]["max_tasks_per_cycle"] = "three"
        errors = validate(write_temp(data))
        self.assertTrue(any("max_tasks_per_cycle" in e for e in errors))


class TestApprovalRequirements(unittest.TestCase):
    def test_safety_commit_requires_human_approval_is_true(self):
        data = load_policy()
        self.assertTrue(data["_safety"]["commit_requires_human_approval"])

    def test_safety_push_requires_human_approval_is_true(self):
        data = load_policy()
        self.assertTrue(data["_safety"]["push_requires_human_approval"])

    def test_policy_commit_requires_human_approval_is_true(self):
        data = load_policy()
        self.assertTrue(data["policy"]["commit_requires_human_approval"])

    def test_policy_push_requires_human_approval_is_true(self):
        data = load_policy()
        self.assertTrue(data["policy"]["push_requires_human_approval"])

    def test_commit_approval_false_caught(self):
        data = load_policy()
        data["policy"]["commit_requires_human_approval"] = False
        errors = validate(write_temp(data))
        self.assertTrue(
            any("commit_requires_human_approval" in e and "must be true" in e for e in errors)
        )

    def test_push_approval_false_caught(self):
        data = load_policy()
        data["policy"]["push_requires_human_approval"] = False
        errors = validate(write_temp(data))
        self.assertTrue(
            any("push_requires_human_approval" in e and "must be true" in e for e in errors)
        )


class TestAllowedRiskLevels(unittest.TestCase):
    def test_allowed_risk_levels_is_low_only(self):
        data = load_policy()
        self.assertEqual(data["policy"]["allowed_risk_levels"], ["LOW"])

    def test_medium_risk_in_allowed_caught(self):
        data = load_policy()
        data["policy"]["allowed_risk_levels"] = ["LOW", "MEDIUM"]
        errors = validate(write_temp(data))
        self.assertTrue(any("allowed_risk_levels" in e for e in errors))

    def test_high_risk_in_allowed_caught(self):
        data = load_policy()
        data["policy"]["allowed_risk_levels"] = ["HIGH"]
        errors = validate(write_temp(data))
        self.assertTrue(any("allowed_risk_levels" in e for e in errors))


class TestProhibitedTaskTypes(unittest.TestCase):
    def test_broker_is_prohibited(self):
        data = load_policy()
        self.assertIn("BROKER", data["policy"]["prohibited_task_types"])

    def test_execution_is_prohibited(self):
        data = load_policy()
        self.assertIn("EXECUTION", data["policy"]["prohibited_task_types"])

    def test_trading_is_prohibited(self):
        data = load_policy()
        self.assertIn("TRADING", data["policy"]["prohibited_task_types"])

    def test_order_is_prohibited(self):
        data = load_policy()
        self.assertIn("ORDER", data["policy"]["prohibited_task_types"])

    def test_broker_removed_from_prohibited_caught(self):
        data = load_policy()
        data["policy"]["prohibited_task_types"].remove("BROKER")
        errors = validate(write_temp(data))
        self.assertTrue(any("BROKER" in e for e in errors))

    def test_broker_in_allowed_types_caught(self):
        data = load_policy()
        data["policy"]["allowed_task_types"].append("BROKER")
        errors = validate(write_temp(data))
        self.assertTrue(any("BROKER" in e for e in errors))


class TestBrokerAccessFields(unittest.TestCase):
    def test_broker_access_allowed_is_false(self):
        data = load_policy()
        self.assertFalse(data["_safety"]["broker_access_allowed"])

    def test_order_access_allowed_is_false(self):
        data = load_policy()
        self.assertFalse(data["_safety"]["order_access_allowed"])

    def test_credential_access_allowed_is_false(self):
        data = load_policy()
        self.assertFalse(data["_safety"]["credential_access_allowed"])


class TestMissingFields(unittest.TestCase):
    def _drop_safety(self, field: str) -> list[str]:
        data = load_policy()
        del data["_safety"][field]
        return validate(write_temp(data))

    def _drop_policy(self, field: str) -> list[str]:
        data = load_policy()
        del data["policy"][field]
        return validate(write_temp(data))

    def test_missing_top_level_safety_caught(self):
        data = load_policy()
        del data["_safety"]
        errors = validate(write_temp(data))
        self.assertTrue(any("_safety" in e for e in errors))

    def test_missing_top_level_policy_caught(self):
        data = load_policy()
        del data["policy"]
        errors = validate(write_temp(data))
        self.assertTrue(any("policy" in e for e in errors))

    def test_missing_execution_allowed_in_safety(self):
        errors = self._drop_safety("execution_allowed")
        self.assertTrue(any("execution_allowed" in e for e in errors))

    def test_missing_execution_allowed_in_policy(self):
        errors = self._drop_policy("execution_allowed")
        self.assertTrue(any("execution_allowed" in e for e in errors))

    def test_missing_max_tasks_per_cycle(self):
        errors = self._drop_policy("max_tasks_per_cycle")
        self.assertTrue(any("max_tasks_per_cycle" in e for e in errors))

    def test_missing_commit_approval(self):
        errors = self._drop_policy("commit_requires_human_approval")
        self.assertTrue(any("commit_requires_human_approval" in e for e in errors))

    def test_missing_push_approval(self):
        errors = self._drop_policy("push_requires_human_approval")
        self.assertTrue(any("push_requires_human_approval" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
