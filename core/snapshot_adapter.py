"""Read-only adapter: load RegimeInput from sibling project snapshots.

Phase 3 — reads existing result_snapshot.json files from NovaBotV2,
NovaAllocationBot, and NovaBotV2Options.  Never writes to those projects.
Falls back to DRY_RUN_INPUTS on any error (missing file, corrupt JSON,
unexpected schema).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput

logger = logging.getLogger(__name__)

# Absolute paths — read-only references to sibling project outputs.
_NOVA_ROOT = Path(__file__).resolve().parents[3]  # C:\NovaGPT

SNAPSHOT_PATHS: dict[str, Path] = {
    "NovaBotV2": _NOVA_ROOT / "Apps" / "NovaBotV2" / "data" / "system" / "result_snapshot.json",
    "NovaAllocationBot": _NOVA_ROOT / "Apps" / "NovaAllocationBot" / "data" / "system" / "result_snapshot.json",
    "NovaBotV2Options": _NOVA_ROOT / "Apps" / "NovaBotV2Options" / "data" / "system" / "result_snapshot.json",
}

_SYNTHETIC_SOURCE = "synthetic_fallback"


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    """Return parsed JSON dict or None on any error (missing, corrupt, wrong type)."""
    try:
        if not path.exists():
            logger.debug("Snapshot not found: %s", path)
            return None
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            logger.warning("Snapshot is not a JSON object: %s", path)
            return None
        return data
    except Exception as exc:
        logger.warning("Failed to load snapshot %s: %s", path, exc)
        return None


def _trend_from_allocation(data: dict[str, Any]) -> float | None:
    """Derive trend_score from NovaAllocationBot recommendation.

    Maps NovaBotV2 allocation percentage (0–100) to trend_score (−1 to +1):
      100 % equity → +1.0 (strongly bullish)
        0 % equity → −1.0 (no equity confidence)
    """
    try:
        alloc = data["recommendation"]["recommended_allocation"]
        novabot_pct = float(alloc["NovaBotV2"])
        trend = round((novabot_pct / 100.0) * 2.0 - 1.0, 3)
        return max(-1.0, min(1.0, trend))
    except Exception as exc:
        logger.debug("Cannot extract trend from allocation snapshot: %s", exc)
        return None


def _volatility_from_options(data: dict[str, Any]) -> float | None:
    """Derive volatility_score from NovaBotV2Options health metrics.

    Uses warnings_count / chains_loaded as a proxy for market friction.
    Clamped to [0, 1].
    """
    try:
        metrics = data["health_metrics"]
        warnings = int(metrics.get("warnings_count", 0))
        chains = max(int(metrics.get("chains_loaded", 1)), 1)
        vol = round(min(1.0, warnings / chains), 3)
        return max(0.0, vol)
    except Exception as exc:
        logger.debug("Cannot extract volatility from options snapshot: %s", exc)
        return None


def load_regime_input_from_snapshots(
    snapshot_paths: dict[str, Path] | None = None,
) -> tuple[RegimeInput, str]:
    """Load RegimeInput from project snapshots.

    Returns (RegimeInput, source_label).
    Falls back to (DRY_RUN_INPUTS, 'synthetic_fallback') on any error.

    This function is read-only — it never writes to any project.
    """
    paths = snapshot_paths if snapshot_paths is not None else SNAPSHOT_PATHS

    allocation_data = _safe_load_json(paths.get("NovaAllocationBot", Path("__missing__")))
    options_data = _safe_load_json(paths.get("NovaBotV2Options", Path("__missing__")))

    trend_score: float | None = None
    volatility_score: float | None = None
    sources: list[str] = []

    if allocation_data is not None:
        trend_score = _trend_from_allocation(allocation_data)
        if trend_score is not None:
            sources.append("NovaAllocationBot")

    if options_data is not None:
        volatility_score = _volatility_from_options(options_data)
        if volatility_score is not None:
            sources.append("NovaBotV2Options")

    if trend_score is None or volatility_score is None:
        logger.info(
            "Snapshot inputs incomplete (trend=%s, vol=%s); using synthetic fallback.",
            trend_score,
            volatility_score,
        )
        return DRY_RUN_INPUTS, _SYNTHETIC_SOURCE

    try:
        inputs = RegimeInput(trend_score=trend_score, volatility_score=volatility_score)
        inputs.validate()
        logger.info(
            "Loaded RegimeInput from snapshots: trend=%.3f vol=%.3f sources=%s",
            trend_score,
            volatility_score,
            sources,
        )
        return inputs, "+".join(sources)
    except Exception as exc:
        logger.warning("RegimeInput from snapshots failed validation: %s", exc)
        return DRY_RUN_INPUTS, _SYNTHETIC_SOURCE
