"""
Autocycle policy offline schema validator.

Validates data/system/autocycle_policy.json for structural correctness and
safety field integrity. Reporting only — no network, no broker, no execution.
"""

import json
import sys
from pathlib import Path

POLICY_PATH = Path(__file__).parent.parent / "data" / "system" / "autocycle_policy.json"

REQUIRED_TOP_LEVEL = {"_schema_version", "_description", "_safety", "policy"}

REQUIRED_SAFETY_FIELDS = {
    "execution_allowed",
    "runtime_effect",
    "informational_only",
    "commit_requires_human_approval",
    "push_requires_human_approval",
    "broker_access_allowed",
    "order_access_allowed",
    "credential_access_allowed",
}

REQUIRED_POLICY_FIELDS = {
    "enabled",
    "informational_only",
    "runtime_effect",
    "execution_allowed",
    "max_tasks_per_cycle",
    "allowed_risk_levels",
    "allowed_task_types",
    "prohibited_task_types",
    "commit_requires_human_approval",
    "push_requires_human_approval",
}

# These must be exactly false in both _safety and policy blocks
SAFETY_MUST_BE_FALSE = {
    "execution_allowed",
    "runtime_effect",
    "broker_access_allowed",
    "order_access_allowed",
    "credential_access_allowed",
}

POLICY_MUST_BE_FALSE = {
    "execution_allowed",
    "runtime_effect",
    "enabled",
}

# These must be exactly true
SAFETY_MUST_BE_TRUE = {
    "informational_only",
    "commit_requires_human_approval",
    "push_requires_human_approval",
}

POLICY_MUST_BE_TRUE = {
    "informational_only",
    "commit_requires_human_approval",
    "push_requires_human_approval",
}


def validate(policy_path: Path = POLICY_PATH) -> list[str]:
    """
    Run all validation checks. Returns a list of error strings.
    Empty list means the policy is valid.
    """
    errors: list[str] = []

    if not policy_path.exists():
        return [f"Policy file not found: {policy_path}"]

    try:
        with open(policy_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    # Fail closed on a structurally invalid top level: a JSON array/scalar/null
    # would AttributeError on data.keys()/data.get(...). Report, never raise.
    if not isinstance(data, dict):
        return ["Top-level policy must be a JSON object"]

    # Top-level keys
    for key in sorted(REQUIRED_TOP_LEVEL - set(data.keys())):
        errors.append(f"Missing top-level key: '{key}'")

    # _safety block
    safety = data.get("_safety", {})
    if not isinstance(safety, dict):
        errors.append("'_safety' must be an object")
    else:
        for key in sorted(REQUIRED_SAFETY_FIELDS - set(safety.keys())):
            errors.append(f"'_safety' missing field: '{key}'")
        for key in SAFETY_MUST_BE_FALSE:
            if key in safety and safety[key] is not False:
                errors.append(f"'_safety.{key}' must be false, got: {safety[key]!r}")
        for key in SAFETY_MUST_BE_TRUE:
            if key in safety and safety[key] is not True:
                errors.append(f"'_safety.{key}' must be true, got: {safety[key]!r}")

    # policy block
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        errors.append("'policy' must be an object")
        return errors

    for key in sorted(REQUIRED_POLICY_FIELDS - set(policy.keys())):
        errors.append(f"'policy' missing field: '{key}'")

    for key in POLICY_MUST_BE_FALSE:
        if key in policy and policy[key] is not False:
            errors.append(f"'policy.{key}' must be false, got: {policy[key]!r}")

    for key in POLICY_MUST_BE_TRUE:
        if key in policy and policy[key] is not True:
            errors.append(f"'policy.{key}' must be true, got: {policy[key]!r}")

    # max_tasks_per_cycle
    mtp = policy.get("max_tasks_per_cycle")
    if mtp is not None:
        if not isinstance(mtp, int):
            errors.append(f"'policy.max_tasks_per_cycle' must be an integer, got: {mtp!r}")
        elif mtp != 3:
            errors.append(
                f"'policy.max_tasks_per_cycle' must be 3, got: {mtp!r}"
            )

    # allowed_risk_levels must be a list containing only "LOW"
    arl = policy.get("allowed_risk_levels")
    if arl is not None:
        if not isinstance(arl, list):
            errors.append("'policy.allowed_risk_levels' must be an array")
        elif arl != ["LOW"]:
            errors.append(
                f"'policy.allowed_risk_levels' must be [\"LOW\"], got: {arl!r}"
            )

    # prohibited_task_types must include the dangerous types
    ptt = policy.get("prohibited_task_types", [])
    if isinstance(ptt, list):
        for required_prohibited in ("BROKER", "EXECUTION", "TRADING", "ORDER"):
            if required_prohibited not in ptt:
                errors.append(
                    f"'policy.prohibited_task_types' must include '{required_prohibited}'"
                )
    else:
        errors.append("'policy.prohibited_task_types' must be an array")

    # allowed_task_types must be a list of strings and not contain dangerous types
    att = policy.get("allowed_task_types", [])
    if isinstance(att, list):
        for dangerous in ("BROKER", "EXECUTION", "TRADING", "ORDER", "CODE"):
            if dangerous in att:
                errors.append(
                    f"'policy.allowed_task_types' must NOT include '{dangerous}'"
                )
    else:
        errors.append("'policy.allowed_task_types' must be an array")

    return errors


def report(errors: list[str]) -> None:
    print("=" * 60)
    print("MarketRegimeBot — Autocycle Policy Validator")
    print(f"Policy:  {POLICY_PATH}")
    print("=" * 60)

    if not errors:
        print("RESULT: PASS — policy is valid")
        print("  No errors found.")
    else:
        print(f"RESULT: FAIL — {len(errors)} error(s) found")
        for err in errors:
            print(f"  ERROR: {err}")

    print("=" * 60)
    print("Safety note: this validator performs no network calls,")
    print("  no broker connections, and no execution side effects.")
    print("  Autocycle execution remains disabled.")
    print("=" * 60)


if __name__ == "__main__":
    errs = validate()
    report(errs)
    sys.exit(0 if not errs else 1)
