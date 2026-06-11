"""Safe regime cycle for MarketRegimeBot — Phase 3 with live market data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput, classify_regime
from core.regime_contracts import (
    RegimeDecision,
    RegimeSafetyState,
    build_unknown_regime_decision,
)
from core.market_data_reader import SOURCE_YFINANCE
from core.snapshot_adapter import load_regime_input_from_snapshots
from core.volatility_classifier import classify_volatility
from utils.regime_export_writer import write_regime_export

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "system" / "result_snapshot.json"


def is_real_market_data(input_source: str) -> bool:
    """Realness rule (REPAIR-005): a regime decision is only ``data_is_real`` when
    it was derived from live market data (yfinance). Every other source —
    ``explicit`` test inputs, ``synthetic_fallback``, ``yfinance_error``, or a
    sibling-snapshot derivation — is fixture/unverified and must be rejected by
    consumers (AllocationBot, TacticBot)."""
    return input_source == SOURCE_YFINANCE


SOURCE_EXPLICIT = "explicit"


def is_trusted_input_source(input_source: str) -> bool:
    """Fail-closed rule (QA-002): only live market data (yfinance) and
    explicitly injected test inputs may be classified into a regime. Every
    fallback source — ``synthetic_fallback``, ``yfinance_error``, sibling-
    snapshot derivations, ``unknown`` — is published as UNKNOWN/confidence 0,
    so a plausible-but-fake regime can never steer a consumer that forgets to
    check ``data_is_real``."""
    return input_source == SOURCE_EXPLICIT or is_real_market_data(input_source)


def write_result_snapshot(
    decision: RegimeDecision,
    result_path: Path = RESULT_SNAPSHOT_PATH,
    *,
    produced_at: str | None = None,
) -> Path:
    resolved_path = result_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved_path.parents and resolved_path != project_root:
        raise ValueError("Refusing to write outside MarketRegimeBot project root.")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(decision.to_dict(produced_at=produced_at), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return result_path


def _build_fallback_unknown_decision(
    inputs: RegimeInput,
    input_source: str,
) -> RegimeDecision:
    """Build the QA-002 fail-closed decision for an untrusted input source.

    The raw scores are preserved under ``fallback_inputs`` for diagnostics
    only — they never reach the classifier, so no plausible fake regime can
    be published."""
    return build_unknown_regime_decision(
        input_source=input_source,
        reason=(
            f"Fail closed (QA-002): input source '{input_source}' is not live "
            "market data or explicit test injection; regime forced to UNKNOWN.",
        ),
        fallback_inputs={
            "trend_score": inputs.trend_score,
            "volatility_score": inputs.volatility_score,
            "synthetic_dry_run_inputs": inputs == DRY_RUN_INPUTS,
        },
    )


def _build_decision_from_inputs(
    inputs: RegimeInput,
    input_source: str = "unknown",
    data_is_real: bool | None = None,
) -> RegimeDecision:
    # QA-002 single choke point: untrusted sources can never be classified.
    if not is_trusted_input_source(input_source):
        return _build_fallback_unknown_decision(inputs, input_source)
    result = classify_regime(inputs)
    vol_result = classify_volatility(inputs.volatility_score)
    real = is_real_market_data(input_source) if data_is_real is None else data_is_real
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
        data_is_real=real,
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
    produced_at: str | None = None,
) -> dict[str, Any]:
    """Run one classification cycle.

    Input priority:
      1. Explicit ``inputs`` argument (tests / overrides).
      2. Live yfinance market data (if ``use_market_data=True``).
      3. Project snapshots via snapshot_adapter (if ``use_snapshot_inputs=True``).
      4. DRY_RUN_INPUTS synthetic fallback.

    Fail-closed publishing (QA-002): only sources 1 (explicit test injection)
    and 2 (yfinance) are classified into a regime. Sources 3 and 4 publish
    UNKNOWN/confidence 0 with the raw scores kept under ``fallback_inputs``.

    Never writes to sibling projects.
    ``_download_fn`` is injected in tests to avoid live network calls.
    ``write_export`` controls whether regime_export.json is written.
    ``produced_at`` (QA-001) is an injectable ISO-8601 UTC timestamp for the
    snapshot freshness envelope; defaults to the current UTC time and is used
    consistently for both the written snapshot and the returned decision dict.
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
    effective_produced_at = (
        produced_at
        if produced_at is not None
        else datetime.now(timezone.utc).isoformat()
    )
    output_path = None
    if write_snapshot:
        output_path = str(
            write_result_snapshot(decision, produced_at=effective_produced_at)
        )
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
        "data_is_real": decision.data_is_real,
        "result_snapshot_path": output_path,
        "regime_export_path": export_path,
        "decision": decision.to_dict(produced_at=effective_produced_at),
    }
