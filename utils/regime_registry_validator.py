"""
Regime registry offline schema validator.

Validates data/system/regime_registry.json for structural correctness.
Does NOT connect to brokers, APIs, or execution systems.
Produces a human-readable report only.
"""

import json
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "system" / "regime_registry.json"

REQUIRED_TOP_LEVEL = {"_schema_version", "_description", "_safety", "regimes"}
REQUIRED_SAFETY_FIELDS = {"execution_authority", "broker_authority", "order_authority", "runtime_effect"}
REQUIRED_REGIME_FIELDS = {
    "id", "label", "enabled", "description",
    "informational_only", "runtime_effect", "execution_authority",
}

SAFETY_MUST_BE_FALSE = {"execution_authority", "broker_authority", "order_authority", "runtime_effect"}
REGIME_MUST_BE_FALSE = {"runtime_effect", "execution_authority"}


def validate(registry_path: Path = REGISTRY_PATH) -> list[str]:
    """
    Run all validation checks. Returns a list of error strings.
    Empty list means the registry is valid.
    """
    errors: list[str] = []

    if not registry_path.exists():
        return [f"Registry file not found: {registry_path}"]

    try:
        with open(registry_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    # Top-level keys
    missing_top = REQUIRED_TOP_LEVEL - set(data.keys())
    for key in sorted(missing_top):
        errors.append(f"Missing top-level key: '{key}'")

    # Safety block
    safety = data.get("_safety", {})
    if not isinstance(safety, dict):
        errors.append("'_safety' must be an object")
    else:
        missing_safety = REQUIRED_SAFETY_FIELDS - set(safety.keys())
        for key in sorted(missing_safety):
            errors.append(f"'_safety' missing field: '{key}'")
        for key in SAFETY_MUST_BE_FALSE:
            if key in safety and safety[key] is not False:
                errors.append(f"'_safety.{key}' must be false, got: {safety[key]!r}")

    # Regimes list
    regimes = data.get("regimes")
    if not isinstance(regimes, list):
        errors.append("'regimes' must be an array")
        return errors

    if len(regimes) == 0:
        errors.append("'regimes' array is empty")

    seen_ids: set[str] = set()
    for idx, regime in enumerate(regimes):
        prefix = f"regimes[{idx}]"

        if not isinstance(regime, dict):
            errors.append(f"{prefix} must be an object")
            continue

        regime_id = regime.get("id", f"<unknown@{idx}>")

        # Duplicate IDs
        if regime_id in seen_ids:
            errors.append(f"{prefix} duplicate id: '{regime_id}'")
        seen_ids.add(regime_id)

        # Required fields
        missing = REQUIRED_REGIME_FIELDS - set(regime.keys())
        for key in sorted(missing):
            errors.append(f"{prefix} (id={regime_id!r}) missing field: '{key}'")

        # Booleans must be false
        for key in REGIME_MUST_BE_FALSE:
            if key in regime and regime[key] is not False:
                errors.append(
                    f"{prefix} (id={regime_id!r}) '{key}' must be false, got: {regime[key]!r}"
                )

        # informational_only must be true
        if "informational_only" in regime and regime["informational_only"] is not True:
            errors.append(
                f"{prefix} (id={regime_id!r}) 'informational_only' must be true, got: {regime['informational_only']!r}"
            )

        # Type checks
        if "enabled" in regime and not isinstance(regime["enabled"], bool):
            errors.append(f"{prefix} (id={regime_id!r}) 'enabled' must be a boolean")
        if "label" in regime and not isinstance(regime["label"], str):
            errors.append(f"{prefix} (id={regime_id!r}) 'label' must be a string")
        if "description" in regime and not isinstance(regime["description"], str):
            errors.append(f"{prefix} (id={regime_id!r}) 'description' must be a string")

    return errors


def report(errors: list[str]) -> None:
    print("=" * 60)
    print("MarketRegimeBot — Regime Registry Validator")
    print(f"Registry: {REGISTRY_PATH}")
    print("=" * 60)

    if not errors:
        print("RESULT: PASS — registry is valid")
        print(f"  No errors found.")
    else:
        print(f"RESULT: FAIL — {len(errors)} error(s) found")
        for err in errors:
            print(f"  ERROR: {err}")

    print("=" * 60)
    print("Safety note: this validator performs no network calls,")
    print("  no broker connections, and no execution side effects.")
    print("=" * 60)


if __name__ == "__main__":
    errs = validate()
    report(errs)
    sys.exit(0 if not errs else 1)
