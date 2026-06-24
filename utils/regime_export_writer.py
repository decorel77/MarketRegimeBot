"""Write the TacticBot-compatible regime export file.

Produces ``data/system/regime_export.json`` from the authoritative
``data/system/result_snapshot.json`` regime payload. The export is a derived
read artifact for NovaTacticBot's market regime adapter (MASTER-020), not a
second source of truth.

Schema: regime_export.v1 - see docs/regime_export_schema.md

Advisory only. Writes only inside MarketRegimeBot project root.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.regime_contracts import RegimeDecision

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGIME_EXPORT_PATH = PROJECT_ROOT / "data" / "system" / "regime_export.json"

EXPORT_SCHEMA_VERSION = "regime_export.v1"
AUTHORITY_ARTIFACT = "data/system/result_snapshot.json"
DERIVED_ARTIFACT = "data/system/regime_export.json"


def _timestamp_from_snapshot(
    snapshot: Mapping[str, Any] | None,
    generated_at: str | None,
) -> str:
    if generated_at:
        return generated_at
    # Guard the container, not just None: this runs before the caller's
    # try/except, so a non-Mapping snapshot (list/scalar/str) must not
    # AttributeError on .get(...) — that would break the "never raises" contract.
    if isinstance(snapshot, Mapping):
        produced_at = snapshot.get("produced_at")
        if isinstance(produced_at, str) and produced_at.strip():
            return produced_at
    return datetime.now(timezone.utc).isoformat()


def _reason_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _unknown_export(generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "project": "MarketRegimeBot",
        "generated_at": generated_at,
        "market_regime": "UNKNOWN",
        "confidence": 0,
        "risk_level": "UNKNOWN",
        "volatility_env": "UNKNOWN",
        "input_source": "unknown",
        "data_is_real": False,
        "reason": ["Export failed - result snapshot authority was invalid"],
        "dry_run": True,
        "read_only": True,
        "runtime_enabled": False,
        "derived_from": AUTHORITY_ARTIFACT,
        "source_schema_version": "unknown",
    }


def build_regime_export_from_result_snapshot(
    snapshot: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the export payload from the authoritative result snapshot.

    Never raises: malformed authority payloads fail closed to UNKNOWN with
    data_is_real=False.
    """
    ts = _timestamp_from_snapshot(snapshot, generated_at)
    try:
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "project": str(snapshot.get("project") or "MarketRegimeBot"),
            "generated_at": ts,
            "market_regime": str(snapshot["market_regime"]),
            "confidence": int(snapshot["confidence"]),
            "risk_level": str(snapshot["risk_level"]),
            "volatility_env": str(snapshot.get("volatility_env") or "UNKNOWN"),
            "input_source": str(snapshot.get("input_source") or "unknown"),
            "data_is_real": bool(snapshot.get("data_is_real")),
            "reason": _reason_list(snapshot.get("reason", [])),
            "dry_run": True,
            "read_only": True,
            "runtime_enabled": False,
            "derived_from": AUTHORITY_ARTIFACT,
            "source_schema_version": str(snapshot.get("schema_version") or "unknown"),
        }
    except Exception:
        return _unknown_export(ts)


def build_regime_export(
    decision: RegimeDecision,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the regime export payload from a RegimeDecision.

    Never raises; returns a safe UNKNOWN export on any error. The decision is
    first serialized into the result-snapshot shape, then the v1 export is
    derived from that authority payload.
    """
    try:
        decision.validate()
        return build_regime_export_from_result_snapshot(
            decision.to_dict(produced_at=generated_at),
            generated_at=generated_at,
        )
    except Exception:
        return _unknown_export(_timestamp_from_snapshot(None, generated_at))


def _assert_export_path_inside_project(export_path: Path) -> None:
    resolved = export_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved.parents and resolved != project_root:
        raise ValueError("Refusing to write regime export outside MarketRegimeBot project root.")


def _write_export_payload(payload: Mapping[str, Any], export_path: Path) -> Path:
    _assert_export_path_inside_project(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return export_path


def write_regime_export_from_result_snapshot(
    snapshot: Mapping[str, Any],
    export_path: Path | None = None,
    *,
    generated_at: str | None = None,
) -> Path:
    """Write the derived export JSON file from result_snapshot authority."""
    # Late-bound default (QA-003): resolved at call time so tests can sandbox
    # REGIME_EXPORT_PATH instead of writing production artifacts.
    if export_path is None:
        export_path = REGIME_EXPORT_PATH
    payload = build_regime_export_from_result_snapshot(
        snapshot,
        generated_at=generated_at,
    )
    return _write_export_payload(payload, export_path)


def write_regime_export(
    decision: RegimeDecision,
    export_path: Path | None = None,
    *,
    generated_at: str | None = None,
) -> Path:
    """Write the derived regime export JSON file.

    Existing callers may still pass a RegimeDecision. It is serialized to the
    result-snapshot shape first so the v1 export remains derived, not separate.
    """
    if export_path is None:
        export_path = REGIME_EXPORT_PATH
    payload = build_regime_export(decision, generated_at=generated_at)
    return _write_export_payload(payload, export_path)
