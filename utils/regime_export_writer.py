"""Write a TacticBot-compatible regime export file.

Produces ``data/system/regime_export.json`` from a ``RegimeDecision``.
This file is the canonical read artifact for NovaTacticBot's market regime
adapter (MASTER-020).

Schema: regime_export.v1 — see docs/regime_export_schema.md

Advisory only. Writes only inside MarketRegimeBot project root.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.regime_contracts import RegimeDecision

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGIME_EXPORT_PATH = PROJECT_ROOT / "data" / "system" / "regime_export.json"

EXPORT_SCHEMA_VERSION = "regime_export.v1"


def build_regime_export(
    decision: RegimeDecision,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the regime export payload from a RegimeDecision.

    Never raises — returns a safe UNKNOWN export on any error.
    ``generated_at`` is injected in tests; defaults to current UTC time.
    """
    try:
        decision.validate()
        ts = generated_at or datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "project": "MarketRegimeBot",
            "generated_at": ts,
            "market_regime": decision.market_regime,
            "confidence": decision.confidence,
            "risk_level": decision.risk_level,
            "volatility_env": decision.volatility_env,
            "input_source": decision.input_source,
            "data_is_real": bool(decision.data_is_real),
            "reason": list(decision.reason),
            "dry_run": True,
            "read_only": True,
            "runtime_enabled": False,
        }
    except Exception:
        ts = generated_at or datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "project": "MarketRegimeBot",
            "generated_at": ts,
            "market_regime": "UNKNOWN",
            "confidence": 0,
            "risk_level": "UNKNOWN",
            "volatility_env": "UNKNOWN",
            "input_source": "unknown",
            "data_is_real": False,
            "reason": ["Export failed — validation error"],
            "dry_run": True,
            "read_only": True,
            "runtime_enabled": False,
        }


def write_regime_export(
    decision: RegimeDecision,
    export_path: Path | None = None,
    *,
    generated_at: str | None = None,
) -> Path:
    """Write the regime export JSON file.

    Only writes inside MarketRegimeBot project root.
    Returns the path written.
    """
    # Late-bound default (QA-003): resolved at call time so the test suite can
    # sandbox REGIME_EXPORT_PATH instead of writing production artifacts.
    if export_path is None:
        export_path = REGIME_EXPORT_PATH
    resolved = export_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved.parents and resolved != project_root:
        raise ValueError("Refusing to write regime export outside MarketRegimeBot project root.")

    payload = build_regime_export(decision, generated_at=generated_at)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return export_path
