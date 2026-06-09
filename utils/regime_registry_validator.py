"""
Regime registry offline schema validator.

Validates data/system/regime_registry.json for structural correctness.
Does NOT connect to brokers, APIs, or execution systems.
Produces a human-readable report only.

Schema versions supported:
  1.0.0 — initial registry
  1.1.0 — added classifier_id, classifier_aligned, scoring_hints, signals
"""

import json
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "system" / "regime_registry.json"

SUPPORTED_SCHEMA_VERSIONS = {"1.0.0", "1.1.0"}

REQUIRED_TOP_LEVEL = {"_schema_version", "_description", "_safety", "regimes"}
REQUIRED_SAFETY_FIELDS = {"execution_authority", "broker_authority", "order_authority", "runtime_effect"}
REQUIRED_REGIME_FIELDS = {
    "id", "label", "enabled", "description",
    "informational_only", "runtime_effect", "execution_authority",
}

# v1.1.0 adds these optional fields — validated when present
V1_1_REGIME_FIELDS = {"classifier_id", "classifier_aligned", "scoring_hints", "signals"}

SAFETY_MUST_BE_FALSE = {"execution_authority", "broker_authority", "order_authority", "runtime_effect"}
REGIME_MUST_BE_FALSE = {"runtime_effect", "execution_authority"}


def _validate_scoring_hints(hints: object, prefix: str, regime_id: str) -> list[str]:
    """Validate the scoring_hints object when present."""
    errors: list[str] = []
    if not isinstance(hints, dict):
        errors.append(f"{prefix} (id={regime_id!r}) 'scoring_hints' must be an object")
        return errors

    required_hint_fields = {"source", "priority", "conditions", "confidence_formula", "risk_level_rule"}
    for field in sorted(required_hint_fields - set(hints.keys())):
        errors.append(f"{prefix} (id={regime_id!r}) 'scoring_hints' missing field: '{field}'")

    conditions = hints.get("conditions")
    if conditions is not None and not isinstance(conditions, list):
        errors.append(f"{prefix} (id={regime_id!r}) 'scoring_hints.conditions' must be an array")
    elif isinstance(conditions, list):
        for i, cond in enumerate(conditions):
            if not isinstance(cond, dict):
                errors.append(f"{prefix} (id={regime_id!r}) 'scoring_hints.conditions[{i}]' must be an object")
            else:
                for required_cond_field in ("field", "operator", "value"):
                    if required_cond_field not in cond:
                        errors.append(
                            f"{prefix} (id={regime_id!r}) 'scoring_hints.conditions[{i}]' "
                            f"missing field: '{required_cond_field}'"
                        )

    return errors


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

    # Schema version
    schema_version = data.get("_schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"Unsupported _schema_version: {schema_version!r}. "
            f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    is_v1_1 = schema_version == "1.1.0"

    # Top-level keys
    for key in sorted(REQUIRED_TOP_LEVEL - set(data.keys())):
        errors.append(f"Missing top-level key: '{key}'")

    # _naming_alignment block (v1.1.0 only — optional but validated when present)
    if is_v1_1 and "_naming_alignment" in data:
        alignment = data["_naming_alignment"]
        if not isinstance(alignment, dict):
            errors.append("'_naming_alignment' must be an object")
        else:
            pairs = alignment.get("misaligned_pairs")
            if pairs is not None and not isinstance(pairs, list):
                errors.append("'_naming_alignment.misaligned_pairs' must be an array")

    # Safety block
    safety = data.get("_safety", {})
    if not isinstance(safety, dict):
        errors.append("'_safety' must be an object")
    else:
        for key in sorted(REQUIRED_SAFETY_FIELDS - set(safety.keys())):
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
        for key in sorted(REQUIRED_REGIME_FIELDS - set(regime.keys())):
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
                f"{prefix} (id={regime_id!r}) 'informational_only' must be true, "
                f"got: {regime['informational_only']!r}"
            )

        # Type checks — core fields
        if "enabled" in regime and not isinstance(regime["enabled"], bool):
            errors.append(f"{prefix} (id={regime_id!r}) 'enabled' must be a boolean")
        if "label" in regime and not isinstance(regime["label"], str):
            errors.append(f"{prefix} (id={regime_id!r}) 'label' must be a string")
        if "description" in regime and not isinstance(regime["description"], str):
            errors.append(f"{prefix} (id={regime_id!r}) 'description' must be a string")

        # v1.1.0 field validation (when present in any schema version)
        if "classifier_id" in regime:
            cid = regime["classifier_id"]
            if cid is not None and not isinstance(cid, str):
                errors.append(
                    f"{prefix} (id={regime_id!r}) 'classifier_id' must be a string or null, "
                    f"got: {cid!r}"
                )

        if "classifier_aligned" in regime:
            ca = regime["classifier_aligned"]
            if ca is not None and not isinstance(ca, bool):
                errors.append(
                    f"{prefix} (id={regime_id!r}) 'classifier_aligned' must be a boolean or null, "
                    f"got: {ca!r}"
                )

        if "scoring_hints" in regime:
            errors.extend(_validate_scoring_hints(regime["scoring_hints"], prefix, regime_id))

        if "signals" in regime:
            sigs = regime["signals"]
            if not isinstance(sigs, list):
                errors.append(f"{prefix} (id={regime_id!r}) 'signals' must be an array")
            else:
                for i, sig in enumerate(sigs):
                    if not isinstance(sig, str):
                        errors.append(
                            f"{prefix} (id={regime_id!r}) 'signals[{i}]' must be a string, "
                            f"got: {sig!r}"
                        )

    return errors


def report(errors: list[str]) -> None:
    print("=" * 60)
    print("MarketRegimeBot — Regime Registry Validator")
    print(f"Registry: {REGISTRY_PATH}")
    print("=" * 60)

    if not errors:
        print("RESULT: PASS — registry is valid")
        print("  No errors found.")
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
