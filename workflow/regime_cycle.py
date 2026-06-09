"""Safe regime cycle for MarketRegimeBot — Phase 3 with live market data."""

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
from core.snapshot_adapter import load_regime_input_from_snapshots
from core.volatility_classifier import classify_volatility
from utils.regime_export_writer import write_regime_export

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


def _build_decision_from_inputs(
    inputs: RegimeInput,
    input_source: str = "unknown",
) -> RegimeDecision:
    result = classify_regime(inputs)
    vol_result = classify_volatility(inputs.volatility_score)
    decision = RegimeDecision(
        project="MarketRegimeBot",
        status="SAFE_DRY_RUN_REGIME",
        market_regime=result.market_regime,
        confidence=result.confidence,
        risk_level=result.risk_level,
        safety=RegimeSafetyState(),
        reason=result.reason,
        volatility_env=vol_result.volatility_env,
        input_source=input_source,
    )
    decision.validate()
    return decision


def run_regime_cycle(
    write_snapshot: bool = True,
    inputs: RegimeInput | None = None,
    use_snapshot_inputs: bool = True,
    use_market_data: bool = True,
    write_export: bool = True,
    _download_fn=None,
) -> dict[str, Any]:
    """Run one classification cycle.

    Input priority:
      1. Explicit ``inputs`` argument (tests / overrides).
      2. Live yfinance market data (if ``use_market_data=True``).
      3. Project snapshots via snapshot_adapter (if ``use_snapshot_inputs=True``).
      4. DRY_RUN_INPUTS synthetic fallback.

    Never writes to sibling projects.
    ``_download_fn`` is injected in tests to avoid live network calls.
    ``write_export`` controls whether regime_export.json is written.
    """
    if inputs is not None:
        effective_inputs = inputs
        input_source = "explicit"
    elif use_market_data:
        from core.market_data_reader import SOURCE_YFINANCE, read_market_regime_inputs
        effective_inputs, input_source = read_market_regime_inputs(_download_fn=_download_fn)
        if input_source != SOURCE_YFINANCE and use_snapshot_inputs:
            # market data failed — try snapshot adapter
            effective_inputs, input_source = load_regime_input_from_snapshots()
    elif use_snapshot_inputs:
        effective_inputs, input_source = load_regime_input_from_snapshots()
    else:
        effective_inputs = DRY_RUN_INPUTS
        input_source = "synthetic_fallback"

    decision = _build_decision_from_inputs(effective_inputs, input_source)
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(decision))
    export_path = None
    if write_export:
        export_path = str(write_regime_export(decision))
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "regime": decision.market_regime,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level,
        "reason": list(decision.reason),
        "volatility_env": decision.volatility_env,
        "input_source": input_source,
        "result_snapshot_path": output_path,
        "regime_export_path": export_path,
        "decision": decision.to_dict(),
    }
