"""Safe dry-run regime cycle for MarketRegimeBot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.regime_contracts import RegimeDecision, build_unknown_regime_decision

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


def run_regime_cycle(write_snapshot: bool = True) -> dict[str, Any]:
    decision = build_unknown_regime_decision()
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(decision))
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "regime": decision.market_regime,
        "confidence": decision.confidence,
        "result_snapshot_path": output_path,
        "decision": decision.to_dict(),
    }

