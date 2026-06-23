"""Dedicated volatility environment classifier for MarketRegimeBot.

Converts a volatility_score (float [0, 1], as produced by market_data_reader)
into a discrete VolatilityEnvironment: HIGH_VOL | NORMAL | LOW_VOL.

Thresholds are calibrated to the VIX mapping in market_data_reader:
  VIX ≤ 15 → vol_score 0.0     → LOW_VOL  (calm)
  VIX ~22.5 → vol_score 0.30   → boundary LOW_VOL / NORMAL
  VIX ~30   → vol_score 0.60   → boundary NORMAL  / HIGH_VOL
  VIX ≥ 40 → vol_score 1.0     → HIGH_VOL (extreme)

Confidence is a 0–100 integer reflecting how far the score is from a
threshold.  Scores near a boundary produce lower confidence.

Pure classifier — no IO, no broker access, advisory only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Constants ------------------------------------------------------------------

VOL_LOW_MAX = 0.30     # vol_score < this  → LOW_VOL
VOL_HIGH_MIN = 0.60    # vol_score >= this → HIGH_VOL
# NORMAL: VOL_LOW_MAX <= vol_score < VOL_HIGH_MIN

VALID_VOL_ENVS = frozenset({"LOW_VOL", "NORMAL", "HIGH_VOL", "UNKNOWN"})

SCHEMA_VERSION = "volatility_classifier.v1"


# --- Result type ----------------------------------------------------------------

@dataclass(frozen=True)
class VolatilityResult:
    volatility_env: str    # LOW_VOL | NORMAL | HIGH_VOL | UNKNOWN
    confidence: int        # 0–100
    vol_score: float       # raw input for traceability
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "volatility_env": self.volatility_env,
            "confidence": self.confidence,
            "vol_score": self.vol_score,
            "reason": self.reason,
            "schema_version": SCHEMA_VERSION,
        }


_UNKNOWN_RESULT = VolatilityResult(
    volatility_env="UNKNOWN",
    confidence=0,
    vol_score=float("nan"),
    reason="vol_score out of valid range or classification failed",
)


# --- Classifier -----------------------------------------------------------------

def classify_volatility(volatility_score: float) -> VolatilityResult:
    """Classify a volatility_score into a VolatilityResult.

    Returns UNKNOWN for scores outside [0, 1].  Never raises.

    Fail-closed on a ``bool`` input: although ``float(True) == 1.0`` and
    ``float(False) == 0.0`` would otherwise classify silently as HIGH_VOL /
    LOW_VOL, a boolean is not a real volatility score.  This mirrors the
    stricter ``risk_classifier._is_real_number`` type gate and yields UNKNOWN
    rather than a fabricated, confident result.
    """
    if isinstance(volatility_score, bool):
        return _UNKNOWN_RESULT
    try:
        v = float(volatility_score)
    except (TypeError, ValueError):
        return _UNKNOWN_RESULT

    if not 0.0 <= v <= 1.0:
        return _UNKNOWN_RESULT

    if v < VOL_LOW_MAX:
        # distance from the LOW/NORMAL boundary → higher confidence when closer to 0
        distance_from_boundary = VOL_LOW_MAX - v
        confidence = min(100, int((distance_from_boundary / VOL_LOW_MAX) * 100))
        return VolatilityResult(
            volatility_env="LOW_VOL",
            confidence=confidence,
            vol_score=round(v, 4),
            reason=f"Volatility score {v:.4f} below low-vol threshold {VOL_LOW_MAX}",
        )

    if v >= VOL_HIGH_MIN:
        # distance above the NORMAL/HIGH boundary
        distance_above = v - VOL_HIGH_MIN
        remaining = 1.0 - VOL_HIGH_MIN
        confidence = min(100, int((distance_above / remaining) * 100))
        return VolatilityResult(
            volatility_env="HIGH_VOL",
            confidence=confidence,
            vol_score=round(v, 4),
            reason=f"Volatility score {v:.4f} at or above high-vol threshold {VOL_HIGH_MIN}",
        )

    # NORMAL: VOL_LOW_MAX <= v < VOL_HIGH_MIN
    mid = (VOL_LOW_MAX + VOL_HIGH_MIN) / 2.0
    distance_from_mid = abs(v - mid)
    half_range = (VOL_HIGH_MIN - VOL_LOW_MAX) / 2.0
    # confidence highest at the midpoint
    confidence = max(0, min(100, int((1.0 - distance_from_mid / half_range) * 70) + 30))
    return VolatilityResult(
        volatility_env="NORMAL",
        confidence=confidence,
        vol_score=round(v, 4),
        reason=(
            f"Volatility score {v:.4f} in normal range "
            f"[{VOL_LOW_MAX}, {VOL_HIGH_MIN})"
        ),
    )
