"""Safe dry-run regime cycle for MarketRegimeBot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput, classify_regime
from core.regime_contracts import (
    RegimeDecision,
    RegimeSafetyState,
    build_unknown_regime_decision,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "system" / "result_snapshot.json"


def write_result_snapshot(
    decision: RegimeDecision,
    result_path: Path = RESULT_SNAPSHOT_PATH,
) -> Path:
    resolved_path = result_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved_path.parents and resolved_path != project_root:
        raise ValueError("Refusing to write outside MarketRegimeBot project root.")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(decision.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result_path


def _build_decision_from_inputs(inputs: RegimeInput) -> RegimeDecision:
    result = classify_regime(inputs)
    decision = RegimeDecision(
        project="MarketRegimeBot",
        status="SAFE_DRY_RUN_REGIME",
        market_regime=result.market_regime,
        confidence=result.confidence,
        risk_level=result.risk_level,
        safety=RegimeSafetyState(),
        reason=result.reason,
    )
    decision.validate()
    return decision


def run_regime_cycle(
    write_snapshot: bool = True,
    inputs: RegimeInput | None = None,
) -> dict[str, Any]:
    """Run one classification cycle.

    Uses DRY_RUN_INPUTS (synthetic) when no inputs are provided.
    """
    effective_inputs = inputs if inputs is not None else DRY_RUN_INPUTS
    decision = _build_decision_from_inputs(effective_inputs)
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(decision))
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "regime": decision.market_regime,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level,
        "reason": list(decision.reason),
        "result_snapshot_path": output_path,
        "decision": decision.to_dict(),
    }
