"""Market regime classification from trend and volatility scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegimeInput:
    trend_score: float      # -1.0 to +1.0; positive = bullish
    volatility_score: float  # 0.0 to 1.0; higher = more volatile

    def validate(self) -> None:
        if not -1.0 <= self.trend_score <= 1.0:
            raise ValueError(f"trend_score must be in [-1, 1], got {self.trend_score}")
        if not 0.0 <= self.volatility_score <= 1.0:
            raise ValueError(
                f"volatility_score must be in [0, 1], got {self.volatility_score}"
            )


@dataclass(frozen=True)
class RegimeResult:
    market_regime: str
    confidence: int         # 0–100
    risk_level: str         # LOW | NORMAL | HIGH
    reason: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_regime": self.market_regime,
            "confidence": self.confidence,
            "risk_level": self.risk_level,
            "reason": list(self.reason),
        }


# Thresholds
_VOLATILITY_HIGH_THRESHOLD = 0.7
_TREND_BULL_THRESHOLD = 0.5
_TREND_BEAR_THRESHOLD = -0.5


def classify_regime(inputs: RegimeInput) -> RegimeResult:
    """Classify market regime from trend and volatility scores.

    Priority order: HIGH_VOLATILITY → BULL → BEAR → SIDEWAYS → UNKNOWN
    """
    inputs.validate()
    t = inputs.trend_score
    v = inputs.volatility_score

    if v > _VOLATILITY_HIGH_THRESHOLD:
        confidence = min(100, int(v * 100))
        return RegimeResult(
            market_regime="HIGH_VOLATILITY",
            confidence=confidence,
            risk_level="HIGH",
            reason=(
                f"Volatility score {v:.2f} exceeds high-volatility threshold "
                f"{_VOLATILITY_HIGH_THRESHOLD}",
            ),
        )

    if t > _TREND_BULL_THRESHOLD:
        confidence = min(100, int(t * 100))
        risk = "NORMAL" if t < 0.85 else "HIGH"
        return RegimeResult(
            market_regime="BULL",
            confidence=confidence,
            risk_level=risk,
            reason=(f"Strong positive trend score {t:.2f}",),
        )

    if t < _TREND_BEAR_THRESHOLD:
        confidence = min(100, int(abs(t) * 100))
        return RegimeResult(
            market_regime="BEAR",
            confidence=confidence,
            risk_level="HIGH",
            reason=(f"Strong negative trend score {t:.2f}",),
        )

    # Low trend and low volatility → sideways
    if abs(t) <= _TREND_BULL_THRESHOLD and v <= _VOLATILITY_HIGH_THRESHOLD:
        # Higher confidence the closer scores are to zero
        confidence = max(
            0, min(100, int((1.0 - abs(t) - v) * 100))
        )
        return RegimeResult(
            market_regime="SIDEWAYS",
            confidence=confidence,
            risk_level="LOW",
            reason=(
                f"Trend score {t:.2f} and volatility score {v:.2f} indicate "
                "range-bound conditions",
            ),
        )

    return RegimeResult(
        market_regime="UNKNOWN",
        confidence=0,
        risk_level="LOW",
        reason=("Could not determine regime from provided scores",),
    )


# Synthetic dry-run inputs used during Phase 2 (no live data)
DRY_RUN_INPUTS = RegimeInput(trend_score=0.8, volatility_score=0.2)
